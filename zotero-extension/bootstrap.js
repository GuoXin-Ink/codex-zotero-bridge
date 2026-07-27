/*
 * Codex Zotero Bridge
 *
 * This extension exposes a small JSON API on Zotero's loopback-only connector
 * server. It never listens on a new network interface. A client must pair with
 * a short-lived code shown in Zotero before it receives a random bearer token.
 *
 * Read operations are available after pairing. Write operations default to
 * dry-run and are rejected unless the user temporarily enables writes from
 * Zotero's Tools menu.
 */

var CodexZoteroBridge = {
  VERSION: "0.1.0",
  ROOT: "/codex-zotero-bridge/v1",
  PREF_TOKEN: "extensions.codexZoteroBridge.v1.token",
  PREF_TOKEN_VERSION: "extensions.codexZoteroBridge.v1.tokenVersion",
  TOKEN_VERSION: 1,
  MAX_REQUEST_CHARS: 1024 * 1024,
  MAX_BATCH_SIZE: 100,
  WRITE_WINDOW_MS: 10 * 60 * 1000,
  PAIR_WINDOW_MS: 2 * 60 * 1000,
  PAIR_MAX_ATTEMPTS: 5,
  ENDPOINTS: [],
  WINDOWS: new Set(),
  pairingCode: null,
  pairingExpiresAt: 0,
  pairingAttempts: 0,
  writeAllowedUntil: 0,

  READ_ACTIONS: new Set([
    "listLibraries",
    "listItems",
    "searchItems",
    "getItem",
    "listCollections",
    "findPotentialDuplicates"
  ]),

  WRITE_ACTIONS: new Set([
    "createItem",
    "updateItem",
    "batchUpdateItems",
    "createCollection",
    "addToCollection",
    "addTags",
    "removeTags",
    "addNote",
    "trashItems"
  ]),

  async startup() {
    await Zotero.initializationPromise;
    if (Zotero.uiReadyPromise) {
      await Zotero.uiReadyPromise;
    }
    this.ensureToken();
    this.registerEndpoints();
    if (Zotero.Server && Zotero.Server.init) {
      Zotero.Server.init();
    }
    for (let win of Zotero.getMainWindows()) {
      this.addToWindow(win);
    }
    Zotero.debug(`[Codex Zotero Bridge] v${this.VERSION} started`);
  },

  shutdown() {
    this.disableWrites();
    this.clearPairing();
    for (let path of this.ENDPOINTS) {
      delete Zotero.Server.Endpoints[path];
    }
    this.ENDPOINTS = [];
    for (let win of Array.from(this.WINDOWS)) {
      this.removeFromWindow(win);
    }
    Zotero.debug("[Codex Zotero Bridge] stopped");
  },

  ensureToken() {
    let token = "";
    let tokenVersion = 0;
    try {
      token = Services.prefs.getStringPref(this.PREF_TOKEN, "");
      tokenVersion = Services.prefs.getIntPref(this.PREF_TOKEN_VERSION, 0);
    }
    catch (_) {}
    if (!token || tokenVersion !== this.TOKEN_VERSION) {
      this.rotateToken(false);
    }
  },

  token() {
    return Services.prefs.getStringPref(this.PREF_TOKEN, "");
  },

  randomBytes(length) {
    const generator = Components.classes[
      "@mozilla.org/security/random-generator;1"
    ].createInstance(Components.interfaces.nsIRandomGenerator);
    const generated = generator.generateRandomBytes(length);
    if (typeof generated === "string") {
      return Array.from(generated, char => char.charCodeAt(0) & 0xff);
    }
    return Array.from(generated);
  },

  randomToken() {
    return this.randomBytes(32)
      .map(value => value.toString(16).padStart(2, "0"))
      .join("");
  },

  randomPairingCode() {
    const bytes = this.randomBytes(4);
    const value = (
      ((bytes[0] << 24) >>> 0) +
      (bytes[1] << 16) +
      (bytes[2] << 8) +
      bytes[3]
    ) >>> 0;
    return String(value % 100000000).padStart(8, "0");
  },

  rotateToken(notify = true, win = null) {
    const token = this.randomToken();
    Services.prefs.setStringPref(this.PREF_TOKEN, token);
    Services.prefs.setIntPref(this.PREF_TOKEN_VERSION, this.TOKEN_VERSION);
    this.clearPairing();
    this.disableWrites();
    if (notify) {
      this.alert(
        win,
        "Codex Zotero Bridge",
        "The connection token was rotated. Existing Codex connections are now disconnected. Start pairing again to reconnect."
      );
    }
    return token;
  },

  constantTimeEqual(left, right) {
    left = String(left || "");
    right = String(right || "");
    let mismatch = left.length ^ right.length;
    const length = Math.max(left.length, right.length);
    for (let index = 0; index < length; index++) {
      mismatch |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
    }
    return mismatch === 0;
  },

  startPairing(win) {
    this.pairingCode = this.randomPairingCode();
    this.pairingExpiresAt = Date.now() + this.PAIR_WINDOW_MS;
    this.pairingAttempts = 0;
    this.copyToClipboard(this.pairingCode);
    this.alert(
      win,
      "Codex Zotero Bridge — Pair Codex",
      `Pairing code: ${this.pairingCode}\n\n` +
      "The code was copied to your clipboard. It expires in 2 minutes and can be used once.\n\n" +
      "In Codex, ask: “Pair Zotero using this code.”"
    );
  },

  clearPairing() {
    this.pairingCode = null;
    this.pairingExpiresAt = 0;
    this.pairingAttempts = 0;
  },

  pairingActive() {
    if (!this.pairingCode || Date.now() >= this.pairingExpiresAt) {
      this.clearPairing();
      return false;
    }
    return true;
  },

  allowWrites(win) {
    const confirmed = Services.prompt.confirm(
      win || null,
      "Codex Zotero Bridge — Enable writes",
      "Allow paired Codex clients to modify this Zotero library for 10 minutes?\n\n" +
      "Review the dry-run result first. Moving items to Trash also requires a separate explicit confirmation."
    );
    if (!confirmed) {
      return;
    }
    this.writeAllowedUntil = Date.now() + this.WRITE_WINDOW_MS;
    this.alert(
      win,
      "Codex Zotero Bridge",
      "Write access is enabled for 10 minutes. You can disable it at any time from the Tools menu."
    );
  },

  disableWrites(win = null, notify = false) {
    this.writeAllowedUntil = 0;
    if (notify) {
      this.alert(win, "Codex Zotero Bridge", "Write access is disabled.");
    }
  },

  writesAllowed() {
    if (Date.now() >= this.writeAllowedUntil) {
      this.writeAllowedUntil = 0;
      return false;
    }
    return true;
  },

  writeSecondsRemaining() {
    if (!this.writesAllowed()) {
      return 0;
    }
    return Math.ceil((this.writeAllowedUntil - Date.now()) / 1000);
  },

  alert(win, title, message) {
    Services.prompt.alert(win || null, title, message);
  },

  copyToClipboard(text) {
    Components.classes["@mozilla.org/widget/clipboardhelper;1"]
      .getService(Components.interfaces.nsIClipboardHelper)
      .copyString(String(text));
  },

  addToWindow(win) {
    if (!win || !win.document || this.WINDOWS.has(win)) {
      return;
    }
    const doc = win.document;
    const toolsPopup = doc.querySelector("#menu_ToolsPopup");
    if (!toolsPopup || doc.querySelector("#codex-zotero-bridge-menu")) {
      return;
    }

    const menu = doc.createXULElement("menu");
    menu.id = "codex-zotero-bridge-menu";
    menu.setAttribute("label", "Codex Zotero Bridge");

    const popup = doc.createXULElement("menupopup");
    const addItem = (id, label, handler) => {
      const item = doc.createXULElement("menuitem");
      item.id = id;
      item.setAttribute("label", label);
      item.addEventListener("command", handler);
      popup.appendChild(item);
      return item;
    };

    addItem(
      "codex-zotero-bridge-pair",
      "Pair Codex…",
      () => this.startPairing(win)
    );
    addItem(
      "codex-zotero-bridge-enable-writes",
      "Allow writes for 10 minutes…",
      () => this.allowWrites(win)
    );
    addItem(
      "codex-zotero-bridge-disable-writes",
      "Disable writes",
      () => this.disableWrites(win, true)
    );

    const separator = doc.createXULElement("menuseparator");
    popup.appendChild(separator);

    addItem(
      "codex-zotero-bridge-status",
      "Connection status…",
      () => {
        const pairing = this.pairingActive() ? "active" : "inactive";
        const writes = this.writesAllowed()
          ? `enabled (${this.writeSecondsRemaining()} seconds remaining)`
          : "disabled";
        this.alert(
          win,
          "Codex Zotero Bridge",
          `Bridge version: ${this.VERSION}\nPairing window: ${pairing}\nWrite access: ${writes}\nEndpoint: 127.0.0.1 only`
        );
      }
    );
    addItem(
      "codex-zotero-bridge-rotate-token",
      "Disconnect all clients and rotate token…",
      () => {
        const confirmed = Services.prompt.confirm(
          win,
          "Codex Zotero Bridge — Rotate token",
          "Disconnect all paired Codex clients and rotate the secret token?"
        );
        if (confirmed) {
          this.rotateToken(true, win);
        }
      }
    );

    menu.appendChild(popup);
    toolsPopup.appendChild(menu);
    this.WINDOWS.add(win);
  },

  removeFromWindow(win) {
    try {
      const menu = win.document.querySelector("#codex-zotero-bridge-menu");
      if (menu) {
        menu.remove();
      }
    }
    catch (_) {}
    this.WINDOWS.delete(win);
  },

  register(path, endpoint) {
    Zotero.Server.Endpoints[path] = endpoint;
    this.ENDPOINTS.push(path);
  },

  registerEndpoints() {
    const bridge = this;

    function StatusEndpoint() {}
    StatusEndpoint.prototype = {
      supportedMethods: ["GET"],
      supportedDataTypes: ["application/json"],
      init(request) {
        const safety = bridge.validateRequest(request, false);
        if (!safety.ok) {
          return bridge.json(safety.status, { ok: false, error: safety.error });
        }
        return bridge.json(200, {
          ok: true,
          bridge: "codex-zotero-bridge",
          version: bridge.VERSION,
          pairingActive: bridge.pairingActive(),
          pairedClientRequired: true,
          writeEnabled: bridge.writesAllowed(),
          writeSecondsRemaining: bridge.writeSecondsRemaining()
        });
      }
    };

    function PairEndpoint() {}
    PairEndpoint.prototype = {
      supportedMethods: ["POST"],
      supportedDataTypes: ["application/json"],
      init(request) {
        const safety = bridge.validateRequest(request, true);
        if (!safety.ok) {
          return bridge.json(safety.status, { ok: false, error: safety.error });
        }
        if (!bridge.pairingActive()) {
          return bridge.json(409, {
            ok: false,
            error: "Pairing is not active. Start pairing from Zotero's Tools menu."
          });
        }
        bridge.pairingAttempts += 1;
        const code = request.data && request.data.code;
        if (!bridge.constantTimeEqual(code, bridge.pairingCode)) {
          if (bridge.pairingAttempts >= bridge.PAIR_MAX_ATTEMPTS) {
            bridge.clearPairing();
          }
          return bridge.json(401, { ok: false, error: "Invalid or expired pairing code." });
        }
        const token = bridge.token();
        bridge.clearPairing();
        Zotero.debug("[Codex Zotero Bridge] client paired");
        return bridge.json(200, {
          ok: true,
          token,
          bridgeVersion: bridge.VERSION,
          writeEnabled: false
        });
      }
    };

    function OperationEndpoint() {}
    OperationEndpoint.prototype = {
      supportedMethods: ["POST"],
      supportedDataTypes: ["application/json"],
      async init(request) {
        const safety = bridge.validateRequest(request, true);
        if (!safety.ok) {
          return bridge.json(safety.status, { ok: false, error: safety.error });
        }
        const auth = bridge.authorize(request);
        if (!auth.ok) {
          return bridge.json(401, { ok: false, error: "Missing or invalid bridge token." });
        }
        const input = request.data || {};
        const action = input.action;
        if (!bridge.READ_ACTIONS.has(action) && !bridge.WRITE_ACTIONS.has(action)) {
          return bridge.json(400, { ok: false, error: "Unknown or missing action." });
        }
        const dryRun = input.dryRun !== false;
        if (bridge.WRITE_ACTIONS.has(action) && !dryRun && !bridge.writesAllowed()) {
          return bridge.json(403, {
            ok: false,
            error: "Write access is disabled. Enable it for 10 minutes from Zotero's Tools menu."
          });
        }
        if (action === "trashItems" && !dryRun && input.confirmation !== "TRASH") {
          return bridge.json(400, {
            ok: false,
            error: "Moving items to Trash requires confirmation=\"TRASH\"."
          });
        }
        try {
          const result = await bridge.runAction(input, dryRun);
          Zotero.debug(
            `[Codex Zotero Bridge] action=${action} dryRun=${dryRun} ok=true`
          );
          return bridge.json(200, {
            ok: true,
            result,
            writeEnabled: bridge.writesAllowed(),
            writeSecondsRemaining: bridge.writeSecondsRemaining()
          });
        }
        catch (error) {
          Zotero.logError(error);
          Zotero.debug(
            `[Codex Zotero Bridge] action=${action} dryRun=${dryRun} ok=false`
          );
          return bridge.json(400, {
            ok: false,
            error: bridge.publicError(error)
          });
        }
      }
    };

    this.register(`${this.ROOT}/status`, StatusEndpoint);
    this.register(`${this.ROOT}/pair`, PairEndpoint);
    this.register(`${this.ROOT}/op`, OperationEndpoint);
  },

  validateRequest(request, requireJSON) {
    const headers = this.normalizedHeaders(request && request.headers);
    const host = headers.host || "";
    if (host && !/^(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$/i.test(host)) {
      return { ok: false, status: 403, error: "Only loopback requests are allowed." };
    }
    if (headers.origin) {
      return { ok: false, status: 403, error: "Browser-originated requests are not allowed." };
    }
    if (requireJSON) {
      const contentType = (headers["content-type"] || "").toLowerCase();
      if (contentType && !contentType.startsWith("application/json")) {
        return { ok: false, status: 415, error: "Content-Type must be application/json." };
      }
      let size = 0;
      try {
        size = JSON.stringify(request.data || {}).length;
      }
      catch (_) {
        return { ok: false, status: 400, error: "Invalid JSON request." };
      }
      if (size > this.MAX_REQUEST_CHARS) {
        return { ok: false, status: 413, error: "Request is too large." };
      }
    }
    return { ok: true };
  },

  normalizedHeaders(headers) {
    const normalized = {};
    for (let [key, value] of Object.entries(headers || {})) {
      normalized[String(key).toLowerCase()] = String(value);
    }
    return normalized;
  },

  authorize(request) {
    const headers = this.normalizedHeaders(request.headers);
    const authorization = headers.authorization || "";
    const prefix = "Bearer ";
    if (!authorization.startsWith(prefix)) {
      return { ok: false };
    }
    return {
      ok: this.constantTimeEqual(authorization.slice(prefix.length), this.token())
    };
  },

  json(status, object) {
    return [
      status,
      {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer"
      },
      JSON.stringify(object)
    ];
  },

  publicError(error) {
    const message = String(error && error.message ? error.message : error);
    return message.slice(0, 500);
  },

  libraryID(input = {}) {
    const value = Number(input.libraryID || Zotero.Libraries.userLibraryID);
    if (!Number.isInteger(value) || value <= 0 || !Zotero.Libraries.get(value)) {
      throw new Error("Unknown libraryID.");
    }
    return value;
  },

  validateLimit(value, fallback = 50, maximum = 200) {
    const number = Number(value === undefined ? fallback : value);
    if (!Number.isInteger(number) || number < 1 || number > maximum) {
      throw new Error(`limit must be an integer from 1 to ${maximum}.`);
    }
    return number;
  },

  validateOffset(value) {
    const number = Number(value || 0);
    if (!Number.isInteger(number) || number < 0) {
      throw new Error("offset must be a non-negative integer.");
    }
    return number;
  },

  validateBatch(values, label) {
    if (!Array.isArray(values) || !values.length) {
      throw new Error(`${label} must be a non-empty array.`);
    }
    if (values.length > this.MAX_BATCH_SIZE) {
      throw new Error(`${label} cannot contain more than ${this.MAX_BATCH_SIZE} entries.`);
    }
    return values;
  },

  async itemByKey(key, libraryID) {
    if (!key || typeof key !== "string") {
      throw new Error("A Zotero item key is required.");
    }
    const item = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, key);
    if (item) {
      await item.loadAllData();
    }
    return item;
  },

  async collectionByKey(key, libraryID) {
    if (!key || typeof key !== "string") {
      throw new Error("A Zotero collection key is required.");
    }
    const collection = await Zotero.Collections.getByLibraryAndKeyAsync(libraryID, key);
    if (collection) {
      await collection.loadAllData();
    }
    return collection;
  },

  summarizeItem(item, includeData = true) {
    const summary = {
      key: item.key,
      id: item.id,
      libraryID: item.libraryID,
      itemType: item.itemType,
      title: item.getField("title"),
      year: item.getField("year"),
      date: item.getField("date"),
      DOI: item.getField("DOI"),
      publicationTitle: item.getField("publicationTitle"),
      url: item.getField("url"),
      deleted: !!item.deleted
    };
    if (includeData) {
      summary.data = item.toJSON ? item.toJSON() : {};
    }
    return summary;
  },

  summarizeCollection(collection) {
    const parent = collection.parentID
      ? Zotero.Collections.get(collection.parentID)
      : null;
    return {
      key: collection.key,
      id: collection.id,
      libraryID: collection.libraryID,
      name: collection.name,
      parentKey: parent ? parent.key : null,
      deleted: !!collection.deleted
    };
  },

  async runAction(input, dryRun) {
    const libraryID = this.libraryID(input);
    switch (input.action) {
      case "listLibraries":
        return this.listLibraries();
      case "listItems":
        return this.listItems(input, libraryID);
      case "searchItems":
        return this.searchItems(input, libraryID);
      case "getItem":
        return this.getItem(input, libraryID);
      case "listCollections":
        return this.listCollections(input, libraryID);
      case "findPotentialDuplicates":
        return this.findPotentialDuplicates(input, libraryID);
      case "createItem":
        return this.createItem(input, libraryID, dryRun);
      case "updateItem":
        return this.updateItem(input, libraryID, dryRun);
      case "batchUpdateItems":
        return this.batchUpdateItems(input, libraryID, dryRun);
      case "createCollection":
        return this.createCollection(input, libraryID, dryRun);
      case "addToCollection":
        return this.addToCollection(input, libraryID, dryRun);
      case "addTags":
        return this.addTags(input, libraryID, dryRun);
      case "removeTags":
        return this.removeTags(input, libraryID, dryRun);
      case "addNote":
        return this.addNote(input, libraryID, dryRun);
      case "trashItems":
        return this.trashItems(input, libraryID, dryRun);
      default:
        throw new Error("Unknown action.");
    }
  },

  listLibraries() {
    const libraries = Zotero.Libraries.getAll()
      .filter(library => library && library.libraryType !== "publications")
      .map(library => ({
        libraryID: library.libraryID,
        name: library.name,
        type: library.libraryType,
        editable: !!library.editable,
        filesEditable: !!library.filesEditable
      }));
    return { libraries };
  },

  async regularItems(libraryID) {
    const ids = await Zotero.Items.getAll(libraryID, true, false, true);
    const items = [];
    for (let id of ids) {
      const item = await Zotero.Items.getAsync(id);
      if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
        continue;
      }
      await item.loadAllData();
      items.push(item);
    }
    return items;
  },

  async listItems(input, libraryID) {
    const limit = this.validateLimit(input.limit, 50, 200);
    const offset = this.validateOffset(input.offset);
    const items = await this.regularItems(libraryID);
    const page = items.slice(offset, offset + limit);
    return {
      total: items.length,
      offset,
      limit,
      hasMore: offset + page.length < items.length,
      items: page.map(item => this.summarizeItem(item, input.includeData !== false))
    };
  },

  async searchItems(input, libraryID) {
    const query = String(input.query || "").trim().toLowerCase();
    if (!query) {
      throw new Error("query is required.");
    }
    const limit = this.validateLimit(input.limit, 25, 100);
    const items = await this.regularItems(libraryID);
    const matches = [];
    for (let item of items) {
      const data = item.toJSON ? item.toJSON() : {};
      const creators = (data.creators || [])
        .map(creator => `${creator.firstName || ""} ${creator.lastName || creator.name || ""}`)
        .join(" ");
      const haystack = [
        item.key,
        item.itemType,
        item.getField("title"),
        item.getField("DOI"),
        item.getField("date"),
        item.getField("publicationTitle"),
        creators,
        (data.tags || []).map(tag => tag.tag).join(" ")
      ].join(" ").toLowerCase();
      if (haystack.includes(query)) {
        matches.push(this.summarizeItem(item, input.includeData !== false));
        if (matches.length >= limit) {
          break;
        }
      }
    }
    return { query: input.query, count: matches.length, items: matches };
  },

  async getItem(input, libraryID) {
    const item = await this.itemByKey(input.key, libraryID);
    if (!item || item.deleted) {
      throw new Error(`Item not found: ${input.key}`);
    }
    const result = this.summarizeItem(item, true);
    if (input.includeChildren) {
      const childIDs = [
        ...item.getAttachments(true),
        ...item.getNotes(true)
      ];
      result.children = [];
      for (let id of childIDs.slice(0, 100)) {
        const child = await Zotero.Items.getAsync(id);
        if (!child || child.deleted) {
          continue;
        }
        await child.loadAllData();
        result.children.push({
          key: child.key,
          id: child.id,
          itemType: child.itemType,
          title: child.getField("title"),
          data: child.toJSON ? child.toJSON() : {}
        });
      }
      result.childrenTruncated = childIDs.length > 100;
    }
    return result;
  },

  async listCollections(input, libraryID) {
    const ids = await Zotero.DB.columnQueryAsync(
      "SELECT collectionID FROM collections WHERE libraryID=? ORDER BY collectionName, collectionID",
      [libraryID]
    );
    const collections = [];
    for (let id of ids) {
      const collection = await Zotero.Collections.getAsync(id);
      if (!collection || collection.deleted) {
        continue;
      }
      await collection.loadAllData();
      collections.push(this.summarizeCollection(collection));
    }
    return { count: collections.length, collections };
  },

  normalizeDOI(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/^https?:\/\/(dx\.)?doi\.org\//, "")
      .replace(/^doi:\s*/, "");
  },

  normalizeTitle(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim()
      .replace(/\s+/g, " ");
  },

  async findPotentialDuplicates(input, libraryID) {
    const limit = this.validateLimit(input.limit, 100, 500);
    const items = await this.regularItems(libraryID);
    const doiGroups = new Map();
    const titleGroups = new Map();

    for (let item of items) {
      const doi = this.normalizeDOI(item.getField("DOI"));
      const title = this.normalizeTitle(item.getField("title"));
      if (doi) {
        if (!doiGroups.has(doi)) doiGroups.set(doi, []);
        doiGroups.get(doi).push(item);
      }
      if (title.length >= 12) {
        if (!titleGroups.has(title)) titleGroups.set(title, []);
        titleGroups.get(title).push(item);
      }
    }

    const groups = [];
    const seen = new Set();
    const addGroups = (map, reason) => {
      for (let [normalizedValue, groupedItems] of map.entries()) {
        if (groupedItems.length < 2) continue;
        const keys = groupedItems.map(item => item.key).sort();
        const signature = keys.join(",");
        if (seen.has(signature)) continue;
        seen.add(signature);
        groups.push({
          reason,
          normalizedValue,
          items: groupedItems.map(item => this.summarizeItem(item, false))
        });
        if (groups.length >= limit) return;
      }
    };
    addGroups(doiGroups, "same DOI");
    if (groups.length < limit) {
      addGroups(titleGroups, "same normalized title");
    }
    return {
      scanned: items.length,
      count: groups.length,
      truncated: groups.length >= limit,
      groups
    };
  },

  ensureEditableLibrary(libraryID) {
    const library = Zotero.Libraries.get(libraryID);
    if (!library || !library.editable) {
      throw new Error("The selected Zotero library is not editable.");
    }
  },

  validateRegularItemType(itemType) {
    if (!itemType || typeof itemType !== "string") {
      throw new Error("data.itemType is required.");
    }
    if (["attachment", "note", "annotation"].includes(itemType)) {
      throw new Error("Only regular bibliographic items can be created.");
    }
    let sample;
    try {
      sample = new Zotero.Item(itemType);
    }
    catch (_) {
      throw new Error(`Unsupported regular item type: ${itemType}`);
    }
    if (!sample.isRegularItem()) {
      throw new Error(`Unsupported regular item type: ${itemType}`);
    }
  },

  async createItem(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const data = input.data;
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error("data must be an item object.");
    }
    this.validateRegularItemType(data.itemType);
    if (dryRun) {
      return { dryRun: true, wouldCreate: data };
    }
    const item = new Zotero.Item(data.itemType);
    item.libraryID = libraryID;
    item.fromJSON(data, { strict: false });
    await item.saveTx();
    return { created: this.summarizeItem(item, true) };
  },

  validateUpdates(updates) {
    if (!updates || typeof updates !== "object" || Array.isArray(updates)) {
      throw new Error("updates must be an object.");
    }
    const allowed = new Set(["fields", "creators", "tags", "collections"]);
    const unknown = Object.keys(updates).filter(key => !allowed.has(key));
    if (unknown.length) {
      throw new Error(`Unsupported update keys: ${unknown.join(", ")}.`);
    }
    if (updates.fields !== undefined &&
        (!updates.fields || typeof updates.fields !== "object" || Array.isArray(updates.fields))) {
      throw new Error("updates.fields must be an object.");
    }
    if (updates.creators !== undefined && !Array.isArray(updates.creators)) {
      throw new Error("updates.creators must be an array.");
    }
    if (updates.tags !== undefined && !Array.isArray(updates.tags)) {
      throw new Error("updates.tags must be an array.");
    }
    if (updates.collections !== undefined && !Array.isArray(updates.collections)) {
      throw new Error("updates.collections must be an array of collection keys.");
    }
  },

  previewUpdate(item, updates) {
    return {
      key: item.key,
      before: this.summarizeItem(item, true),
      updates
    };
  },

  async applyUpdates(item, updates, libraryID) {
    this.validateUpdates(updates);
    if (updates.fields) {
      for (let [field, value] of Object.entries(updates.fields)) {
        item.setField(field, value === null ? "" : value);
      }
    }
    if (updates.creators) {
      item.setCreators(updates.creators);
    }
    if (updates.tags) {
      item.setTags(
        updates.tags.map(tag =>
          typeof tag === "string" ? { tag, type: 0 } : tag
        )
      );
    }
    if (updates.collections) {
      const collectionIDs = [];
      for (let key of updates.collections) {
        const collection = await this.collectionByKey(key, libraryID);
        if (!collection || collection.deleted) {
          throw new Error(`Collection not found: ${key}`);
        }
        collectionIDs.push(collection.id);
      }
      item.setCollections(collectionIDs);
    }
    await item.saveTx();
    return this.summarizeItem(item, true);
  },

  async updateItem(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const item = await this.itemByKey(input.key, libraryID);
    if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
      throw new Error(`Regular item not found: ${input.key}`);
    }
    this.validateUpdates(input.updates);
    if (dryRun) {
      return { dryRun: true, wouldUpdate: this.previewUpdate(item, input.updates) };
    }
    const updated = await this.applyUpdates(item, input.updates, libraryID);
    return { updated };
  },

  async batchUpdateItems(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const changes = this.validateBatch(input.changes, "changes");
    const previews = [];
    const resolved = [];
    for (let change of changes) {
      if (!change || typeof change !== "object") {
        throw new Error("Each change must be an object.");
      }
      const item = await this.itemByKey(change.key, libraryID);
      if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
        throw new Error(`Regular item not found: ${change.key}`);
      }
      this.validateUpdates(change.updates);
      previews.push(this.previewUpdate(item, change.updates));
      resolved.push({ item, updates: change.updates });
    }
    if (dryRun) {
      return { dryRun: true, count: previews.length, wouldUpdate: previews };
    }
    const updated = [];
    for (let entry of resolved) {
      updated.push(await this.applyUpdates(entry.item, entry.updates, libraryID));
    }
    return { count: updated.length, updated };
  },

  async createCollection(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const name = String(input.name || "").trim();
    if (!name) {
      throw new Error("name is required.");
    }
    let parentID = null;
    if (input.parentKey) {
      const parent = await this.collectionByKey(input.parentKey, libraryID);
      if (!parent || parent.deleted) {
        throw new Error(`Parent collection not found: ${input.parentKey}`);
      }
      parentID = parent.id;
    }
    if (dryRun) {
      return {
        dryRun: true,
        wouldCreateCollection: { name, parentKey: input.parentKey || null }
      };
    }
    const collection = new Zotero.Collection();
    collection.libraryID = libraryID;
    collection.name = name;
    if (parentID) collection.parentID = parentID;
    await collection.saveTx();
    return { created: this.summarizeCollection(collection) };
  },

  async addToCollection(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const keys = this.validateBatch(input.keys, "keys");
    const collection = await this.collectionByKey(input.collectionKey, libraryID);
    if (!collection || collection.deleted) {
      throw new Error(`Collection not found: ${input.collectionKey}`);
    }
    const items = [];
    for (let key of keys) {
      const item = await this.itemByKey(key, libraryID);
      if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
        throw new Error(`Regular item not found: ${key}`);
      }
      items.push(item);
    }
    if (dryRun) {
      return {
        dryRun: true,
        wouldAdd: keys,
        collection: this.summarizeCollection(collection)
      };
    }
    for (let item of items) {
      item.addToCollection(collection.id);
      await item.saveTx({ skipDateModifiedUpdate: true });
    }
    return { added: keys, collectionKey: collection.key };
  },

  async addTags(input, libraryID, dryRun) {
    return this.changeTags(input, libraryID, dryRun, false);
  },

  async removeTags(input, libraryID, dryRun) {
    return this.changeTags(input, libraryID, dryRun, true);
  },

  async changeTags(input, libraryID, dryRun, remove) {
    this.ensureEditableLibrary(libraryID);
    const keys = this.validateBatch(input.keys, "keys");
    const tags = this.validateBatch(input.tags, "tags")
      .map(tag => String(tag).trim())
      .filter(Boolean);
    if (!tags.length) {
      throw new Error("tags must contain non-empty strings.");
    }
    const items = [];
    for (let key of keys) {
      const item = await this.itemByKey(key, libraryID);
      if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
        throw new Error(`Regular item not found: ${key}`);
      }
      items.push(item);
    }
    if (dryRun) {
      return {
        dryRun: true,
        operation: remove ? "removeTags" : "addTags",
        keys,
        tags
      };
    }
    for (let item of items) {
      for (let tag of tags) {
        if (remove) item.removeTag(tag);
        else item.addTag(tag, 0);
      }
      await item.saveTx({ skipDateModifiedUpdate: true });
    }
    return {
      operation: remove ? "removeTags" : "addTags",
      keys,
      tags
    };
  },

  async addNote(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const item = await this.itemByKey(input.key, libraryID);
    if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
      throw new Error(`Regular item not found: ${input.key}`);
    }
    const noteHTML = String(input.noteHTML || "").trim();
    if (!noteHTML || noteHTML.length > 100000) {
      throw new Error("noteHTML is required and must be at most 100,000 characters.");
    }
    if (dryRun) {
      return {
        dryRun: true,
        wouldAddNoteTo: item.key,
        noteLength: noteHTML.length
      };
    }
    const note = new Zotero.Item("note");
    note.libraryID = libraryID;
    note.parentID = item.id;
    note.setNote(noteHTML);
    await note.saveTx();
    return { createdNoteKey: note.key, parentKey: item.key };
  },

  async trashItems(input, libraryID, dryRun) {
    this.ensureEditableLibrary(libraryID);
    const keys = this.validateBatch(input.keys, "keys");
    const items = [];
    for (let key of keys) {
      const item = await this.itemByKey(key, libraryID);
      if (!item || item.deleted || !item.isRegularItem || !item.isRegularItem()) {
        throw new Error(`Regular item not found: ${key}`);
      }
      items.push(item);
    }
    const previews = items.map(item => this.summarizeItem(item, false));
    if (dryRun) {
      return { dryRun: true, wouldMoveToTrash: previews };
    }
    await Zotero.Items.trashTx(items.map(item => item.id));
    return { movedToTrash: previews };
  }
};

function install(data, reason) {}

async function startup(data, reason) {
  await CodexZoteroBridge.startup();
}

async function onMainWindowLoad({ window }, reason) {
  CodexZoteroBridge.addToWindow(window);
}

function onMainWindowUnload({ window }, reason) {
  CodexZoteroBridge.removeFromWindow(window);
}

function shutdown(data, reason) {
  if (reason === APP_SHUTDOWN) return;
  CodexZoteroBridge.shutdown();
}

function uninstall(data, reason) {}
