.PHONY: validate test build clean

validate:
	python3 scripts/validate.py

test:
	python3 -m unittest discover -s tests -v

build: validate
	python3 scripts/build_xpi.py

clean:
	rm -rf build dist
