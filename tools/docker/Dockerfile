# Use an official Ubuntu as a base image
FROM ubuntu:22.04

# Set the environment to non-interactive to avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Update and install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    make \
    autoconf \
    automake \
    bison \
    flex \
    gcc \
    g++ \
    gawk \
    libncurses5-dev \
    pkg-config \
    libconfuse-dev \
    libssl-dev \
    python3 \
    python3-pip \
    python-is-python3 \
    cmake \
    libyaml-dev \
    scons \
    mtools \
    bzip2 \
    curl \
    git \
    openssh-client \
    rsync \
    dosfstools \
    ca-certificates \
    && apt-get clean && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install required Python packages
RUN pip3 install pycryptodome gmssl scons==3.1.2

# Set up the repo tool for managing the source code
RUN mkdir -p ~/.bin && \
    curl https://storage.googleapis.com/git-repo-downloads/repo > ~/.bin/repo && \
    chmod a+rx ~/.bin/repo && \
    echo 'export PATH="${HOME}/.bin:${PATH}"' >> ~/.bashrc

# Create base directories for the toolchains
RUN mkdir -p ~/.kendryte/k230_toolchains/

# Download and extract the RISC-V toolchain
RUN curl -L https://kendryte-download.canaan-creative.com/k230/toolchain/riscv64-unknown-linux-musl-rv64imafdcv-lp64d-20230420.tar.bz2 -o /root/.kendryte/k230_toolchains/riscv64-unknown-linux-musl-rv64imafdcv-lp64d-20230420.tar.bz2 && \
    tar xf /root/.kendryte/k230_toolchains/riscv64-unknown-linux-musl-rv64imafdcv-lp64d-20230420.tar.bz2 -C /root/.kendryte/k230_toolchains/ && \
    rm -rf /root/.kendryte/k230_toolchains/riscv64-unknown-linux-musl-rv64imafdcv-lp64d-20230420.tar.bz2

# Download and extract the Xuantie-900 toolchain
RUN curl -L https://kendryte-download.canaan-creative.com/k230/toolchain/Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0.tar.bz2 -o /root/.kendryte/k230_toolchains/Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0.tar.bz2 && \
    tar xf /root/.kendryte/k230_toolchains/Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0.tar.bz2 -C /root/.kendryte/k230_toolchains/ && \
    rm -rf /root/.kendryte/k230_toolchains/Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0.tar.bz2

# Set the working directory for the project
WORKDIR /workspace

# Persist PATH for future sessions
RUN /bin/bash -c "source ~/.bashrc"
