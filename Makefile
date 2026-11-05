HOST ?= zuvat

.PHONY: image test card flash seed-preview ssh info

image: ## build build/zuvat-YYYYMMDD.img.xz, then run the first-boot test
	image/build.sh

test: ## first-boot test of the newest image (or IMG=build/x.img.xz)
	image/test.sh $(IMG)

card: ## pick an SD card from a list, confirm, then flash the newest image [ARGS="-n NAME -i IP"]
	image/flash.sh $(ARGS)

flash: ## write the newest image to a named card: make flash DISK=/dev/diskN [ARGS="-i 192.168.4.x"]
	image/flash.sh -d $(DISK) $(ARGS)

seed-preview: ## render the cloud-init seed into build/seed-preview (contains secrets; build/ is ignored)
	mkdir -p build/seed-preview && image/seed.sh build/seed-preview $(ARGS)

ssh:
	ssh jtl@$(HOST).local

info: ## what the running Pi was built from
	ssh jtl@$(HOST).local 'cat /etc/zuvat-image/release; mbregistry --version'
