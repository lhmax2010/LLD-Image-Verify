PWD := $(shell pwd)

LOGGER_MAIN_BUFFER_SIZE ?= 256
LOGGER_EVENTS_BUFFER_SIZE ?= 256
LOGGER_RADIO_BUFFER_SIZE ?= 256
LOGGER_SYSTEM_BUFFER_SIZE ?= 256

THREAD_GROUP_CPUTIME_SUPPORT ?= 0

TIZEN_INFORM_PATH ?= "/mnt/inform/reboot-param.bin"

# See commit 0b999ae3614d0 ("Merge tag 'compiler-attributes-for-linus-v5.0-rc7'"[..]) for rationale
CFLAGS_logger.o   += -Wno-error=missing-attributes \
	-DLOGGER_MAIN_BUFFER_SIZE=$(LOGGER_MAIN_BUFFER_SIZE) \
	-DLOGGER_EVENTS_BUFFER_SIZE=$(LOGGER_EVENTS_BUFFER_SIZE) \
	-DLOGGER_RADIO_BUFFER_SIZE=$(LOGGER_RADIO_BUFFER_SIZE) \
	-DLOGGER_SYSTEM_BUFFER_SIZE=$(LOGGER_SYSTEM_BUFFER_SIZE)
CFLAGS_proc-tsm.o += -Wno-error=missing-attributes \
		     -DTHREAD_GROUP_CPUTIME_SUPPORT=$(THREAD_GROUP_CPUTIME_SUPPORT)
CFLAGS_inform-reboot.o += -DTIZEN_INFORM_PATH="\"$(TIZEN_INFORM_PATH)\""

# Build is disabled by default so that when new module is added to this repository (and -source package),
# it won't get automatically build in packages using it (that would break these automatically as file list
# would no longer match).
BUILD_dm_bow ?= n
BUILD_extcon_usb_fixed ?= n
BUILD_inform_reboot ?= n
BUILD_logger ?= n
BUILD_proc_tsm ?= n
BUILD_kdbus ?= n
BUILD_zlogger ?= n

obj-$(BUILD_dm_bow) += dm-bow.o
obj-$(BUILD_extcon_usb_fixed) += extcon-usb-fixed.o
obj-$(BUILD_inform_reboot) += inform-reboot.o
obj-$(BUILD_logger) += logger.o
obj-$(BUILD_proc_tsm) += proc-tsm.o
obj-$(BUILD_kdbus) += kdbus/
obj-$(BUILD_zlogger) += zlogger/

all:
	make -C $(KERNELDIR) M=$(PWD) CFLAGS_MODULE=-I$(PWD)/include modules

modules_install:
	make -C $(KERNELDIR) M=$(PWD) INSTALL_MOD_STRIP=$(INSTALL_MOD_STRIP) INSTALL_MOD_PATH=$(PWD)/../$(INSTALL_MOD_PATH) modules_install

clean:
	make -C $(KERNELDIR) M=$(PWD) clean
