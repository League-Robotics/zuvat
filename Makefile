HOST ?= zuvat

.PHONY: image flash seed-preview ssh info

image: ## build build/zuvat-YYYYMMDD.img.xz
	image/build.sh

flash: ## write the newest image to a card: make flash DISK=/dev/diskN [ARGS="-i 192.168.4.x"]
	image/flash.sh -d $(DISK) $(ARGS)

seed-preview: ## render the cloud-init seed into build/seed-preview (contains secrets; build/ is ignored)
	mkdir -p build/seed-preview && image/seed.sh build/seed-preview $(ARGS)

ssh:
	ssh jtl@$(HOST).local

info: ## what the running Pi was built from
	ssh jtl@$(HOST).local 'cat /etc/zuvat-image/release; mbregistry --version'
