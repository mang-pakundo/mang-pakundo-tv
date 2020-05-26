SRC_DIR := src
BUILD_DIR := build
OPS_DIR := ops
VENV_DIR ?= virtualenv
ADDON_NAME := $(shell xmllint --xpath "/addon/@id" "$(SRC_DIR)/addon.xml" | sed 's/.*id="\(..*\)"/\1/')
VERSION := $(shell xmllint --xpath "/addon/@version" "$(SRC_DIR)/addon.xml" | sed 's/.*version="\(..*\)"/\1/')
ARTIFACT_NAME := $(ADDON_NAME)-$(VERSION)

export VERSION

.PHONY: build clean data init clean-version release

data: init
	@(source $(VENV_DIR)/bin/activate && python $(OPS_DIR)/mkdata.py $(OPS_DIR)/config.json $(BUILD_DIR)/data.py $(BUILD_DIR)/data.dat)
	@mv $(BUILD_DIR)/data.py $(SRC_DIR)/lib/data.py

build: init data
	@mkdir -p $(BUILD_DIR)/$(ADDON_NAME)/lib
	@cp $(SRC_DIR)/addon.xml $(SRC_DIR)/default.py $(SRC_DIR)/icon.png $(BUILD_DIR)/$(ADDON_NAME)
	@cp $(SRC_DIR)/lib/*.py $(BUILD_DIR)/$(ADDON_NAME)/lib
	@cp -R $(SRC_DIR)/resources $(BUILD_DIR)/$(ADDON_NAME)
	@cd $(BUILD_DIR) && zip -r $(ARTIFACT_NAME).zip $(ADDON_NAME)

# this requires the .env file with the RELEASE_DIR defined
release: build
	@(source .env && cp $(BUILD_DIR)/$(ARTIFACT_NAME).zip "$$RELEASE_REPO/downloads/$(ADDON_NAME)" && cp ../addons.xml ../addons.xml.md5 "$$RELEASE_REPO" && cp $(BUILD_DIR)/data.dat "$$RELEASE_REPO/resources/data/$(ADDON_NAME)")

version: init
ifndef BUMP
	$(error Specify major, minor or patch to indicate which segment to bump. E.g.: BUMP=patch)
endif
	@(source $(VENV_DIR)/bin/activate && python $(OPS_DIR)/mksemver.py $(SRC_DIR)/addon.xml ../addons.xml $(BUMP))
	cd .. && md5sum addons.xml > addons.xml.md5

clean-version:
	git checkout $(SRC_DIR)/addon.xml ../addons.xml ../addons.xml.md5

init:
	@mkdir -p $(BUILD_DIR)

clean: clean-version
	@rm -rf $(BUILD_DIR)
