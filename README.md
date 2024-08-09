# How to build

## Requirments

```shell
sudo apt install bison flex gcc libncurses5-dev pkg-config libconfuse-dev libssl-dev python3 python3-pip python-is-python3 cmake libyaml-dev scons mtools

pip3 install pycryptodome gmssl
```

## Build

```shell
repo init -u https://github.com/canmv-k230/manifest
repo sync

# optional
make dl_toolchain

make k230_canmv_defconfig # or other board defconfig
make
```
