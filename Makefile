MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

RUN_TAG = $(shell ls librelane/runs/ | tail -n 1)
TOP = chip_top

PDK_ROOT ?= $(MAKEFILE_DIR)/gf180mcu
PDK ?= gf180mcuD
PDK_COMMIT ?= f3b5e46babb6b417f9a1a1b5c413f7dda6f68a51

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
.PHONY: help

all: clone-pdk ## Default target
.PHONY: all

$(PDK_ROOT)/$(PDK):
	ciel enable $(PDK_COMMIT) --pdk-root $(PDK_ROOT) --pdk-family $(PDK)

clone-pdk: $(PDK_ROOT)/$(PDK) ## Clone the gf180mcu PDK
.PHONY: clone-pdk

gf180mcu-example-layouts:
	git clone https://github.com/wafer-space/gf180mcu-example-layouts.git

clone-layouts: gf180mcu-example-layouts
.PHONY: clone-layouts

precheck: clone-pdk clone-layouts
	python3 precheck.py --slot ${SLOT} --cob --input gf180mcu-example-layouts/${DOMAIN}/${SLOT}/${TOP}.oas --id DEADBEEF --workers max --threads 1 --output ${TOP}.oas
.PHONY: precheck

precheck-no-cob: clone-pdk clone-layouts
	python3 precheck.py --slot ${SLOT} --input gf180mcu-example-layouts/${DOMAIN}/${SLOT}/${TOP}.oas --id DEADBEEF --workers max --threads 1 --output ${TOP}.oas
.PHONY: precheck-no-cob
