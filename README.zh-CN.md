# Codex Zotero Bridge

[English](README.md)

Codex Zotero Bridge 用于让本地 Codex 安全地查看、整理和修改同一台电脑上的 Zotero。它的定位是 Zotero 文献库管理，和 LaTeX 没有绑定关系，也不依赖某一种写作或引用流程。

本仓库包含两个相互配合的组件：

1. Zotero 扩展（`.xpi`）：在 Zotero 已有的本地回环服务器上提供一个小型、需要认证的接口；
2. Codex 插件：包含本地 MCP server 和一套强调安全审核的 Zotero skill。

不需要项目方提供的云服务或付费 API key。本项目使用 MIT License，免费开源。

> [!IMPORTANT]
> Zotero 扩展可以访问你的 Zotero 数据。请先检查源码，只安装你信任的版本；在批量自动化之前，也请备份重要文献库。

## 可以做什么

- 列出和搜索文献条目
- 读取完整 Zotero 元数据，以及按需读取子条目元数据
- 列出文献库和分类文件夹
- 查找 DOI 完全相同或规范化标题相同的疑似重复项
- 预览并修改元数据、作者等字段
- 新建普通文献条目和分类文件夹
- 把条目加入分类文件夹
- 添加或删除标签
- 添加子笔记
- 把你明确同意的条目移入 Zotero 回收站

它有意不提供以下能力：永久删除、读取附件文件内容、导入任意本地文件、自动合并重复项、从外网自动抓取元数据。

## 环境要求

- Zotero 8 或 9；当前实际测试版本为 Zotero 9.0.6
- Codex 所在环境中安装 Python 3.9 或更高版本
- 支持插件和 stdio MCP server 的本地 Codex 客户端

Codex 使用桥接器时，Zotero 必须保持运行。Codex 云端环境无法直接访问你个人电脑上的 Zotero。

## 安装

### 1. 安装 Zotero 扩展

1. 从最新 GitHub Release 下载 `codex-zotero-bridge-0.1.0.xpi`。
2. 在 Zotero 中打开 **Tools > Add-ons**。
3. 点击齿轮菜单，选择 **Install Add-on From File…**，然后选择 XPI。
4. 重启 Zotero。

如果要从源码构建：

```bash
git clone https://github.com/GuoXin-Ink/codex-zotero-bridge.git
cd codex-zotero-bridge
python3 scripts/build_xpi.py
```

然后安装 `dist/` 中生成的 XPI。

### 2. 安装 Codex 插件

```bash
codex plugin marketplace add GuoXin-Ink/codex-zotero-bridge
codex plugin add codex-zotero-bridge@codex-zotero-bridge
```

安装后重启 Codex。同一个 host 上的 Codex CLI 和 IDE 扩展共享插件配置。

### 3. 配对

1. 保持 Zotero 运行。
2. 在 Zotero 中选择 **Tools > Codex Zotero Bridge > Pair Codex…**。
3. Zotero 会生成并复制一个一次性的 8 位配对码；它在 2 分钟后失效。
4. 告诉 Codex：`使用这个配对码连接 Zotero：12345678`。

长期随机令牌只保存在本机配置文件中；在系统支持时，文件权限会限制为仅当前用户可读。令牌不会显示给模型。

## 使用示例

你可以直接这样说：

```text
我的 Zotero My Library 一共有多少条记录？按文献类型汇总。
找出疑似重复条目，但不要做任何修改。
检查 Kaufmann 这篇文章的元数据并提出修改建议。
预览把这些标题改成 sentence case，注意保留缩写。
新建一个叫 Reviewed 的分类，并把选中的条目放进去。
找出可能的预印本，并说明它们是否已有正式发表版本。
```

读取操作只需要已经完成配对。真正修改时，Codex 应该遵循下面的流程：

1. 重新读取当前条目；
2. 使用 dry-run 预演修改；
3. 把准确的修改内容展示给你并等待明确同意；
4. 请你在 Zotero 中选择 **Tools > Codex Zotero Bridge > Allow writes for 10 minutes…**；
5. 只应用已审核的修改；
6. 再次读取条目，核对最终结果。

写权限默认关闭，10 分钟后自动失效，并且每次重启 Zotero 都会恢复为关闭。移入回收站还需要桥接器额外验证 `TRASH` 确认。你可以随时在 Zotero 的同一菜单里立即关闭写权限或断开全部客户端。

## WSL 使用

常见配置是：Windows 中运行 Zotero，WSL 中运行 Codex 和 Python。MCP server 会先尝试 WSL 的 loopback；如果不可用，它会自动通过 Windows PowerShell 发出同样的 Windows 本地回环请求。Bearer token 通过标准输入传递，不会出现在进程参数里。

可以先检查：

```bash
python3 --version
powershell.exe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
```

两条命令都应该输出版本信息。普通使用者不需要手工启动 MCP server。

如果 Codex 仍然无法连接：

- 确认 Windows 中的 Zotero 正在运行，扩展也已经启用；
- 更新 WSL，并执行 `wsl --shutdown` 后重新打开；
- 确认 WSL 中可以运行 `powershell.exe`；
- 也可以启用 Windows 与 WSL 的 localhost forwarding 或 mirrored networking；
- 检查安全软件是否拦截 Zotero 的本地 connector 端口。

不要把 23119 端口通过端口转发、反向代理、隧道或公网防火墙规则暴露出去。

## 安全机制

扩展不会新开公网监听端口，而是在 Zotero 自己的本地 connector server 上注册接口。它会拒绝非回环 Host、浏览器 `Origin`、非 JSON 修改请求、过大的请求、未认证操作、未开放写权限时的修改，以及未明确确认的回收站操作。

配对码和 bearer token 主要防止误连接或未经配对的访问。如果操作系统当前用户账号本身已经被攻破，本项目无法继续保护该账号下的 Zotero。详细说明见 [SECURITY.md](SECURITY.md)、[PRIVACY.md](PRIVACY.md) 和 [docs/threat-model.md](docs/threat-model.md)。

## 开发与验证

```bash
python3 scripts/validate.py
python3 scripts/build_xpi.py
```

`validate.py` 会运行单元测试、静态安全检查、Python 语法检查、JSON 检查，并在相应工具存在时运行 Codex plugin 和 skill 验证器。

XPI 中只有两个文件：

```text
manifest.json
bootstrap.js
```

实现细节见 [docs/architecture.md](docs/architecture.md) 和 [docs/protocol.md](docs/protocol.md)。

## 当前限制

- Zotero 端使用扩展内部 API，未来 Zotero 大版本更新时可能需要适配。
- 0.1.0 的 manifest 允许 Zotero 8 和 9，但当前只在 Zotero 9.0.6 上实际测试。
- DOI 或标题相同只能说明“疑似重复”，不能直接证明应该删除。
- 本项目与 Zotero、OpenAI 均无隶属或官方认可关系。

## License

MIT
