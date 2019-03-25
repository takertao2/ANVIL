#!/bin/bash

onred='\033[41m'
ongreen='\033[42m'
onyellow='\033[43m'
endcolor="\033[0m"

# Handle errors
set -e
error_report() {
    echo -e "${onred}Error: failed on line $1.$endcolor"
}
trap 'error_report $LINENO' ERR

# Script functions
get_latest() {
    if [ ! -d $2 ]; then
        git clone https://github.com/$1/$2.git --recursive
        cd $2
    else
        cd $2
        git pull
    fi
    cd ..
}


##### CORE DEPENDENCIES #####

echo -e "${onyellow}Installing core tools...$endcolor"

if [[ "$OSTYPE" == "linux-gnu" ]]; then
    yes | sudo apt-get install build-essential \
                               git \
                               cmake \
                               python3 \
                               python3-pip \
                               python3-pytest
    # Python 3.7 for Quart
    yes | sudo apt install software-properties-common
    yes | sudo add-apt-repository ppa:deadsnakes/ppa
    yes | sudo apt install python3.7
elif [[ "$OSTYPE" == "darwin"* ]]; then
    xcode-select --version || xcode-select --install
    brew --version || yes | /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    python3.7 --version || brew install python
    cmake --version || brew install cmake
fi

pip3 install --upgrade setuptools
pip3 install wheel


##### FETCH #####

echo -e "${onyellow}Installing Fetch...$endcolor"

if [[ "$OSTYPE" == "linux-gnu" ]]; then
    yes | sudo apt-get install python3-sphinx \
                               protobuf-compiler \
                               libprotobuf-dev \
                               tox
    pip3 install gitpython
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew upgrade protobuf || brew install protobuf
fi

# Install OEFPython
get_latest fetchai oef-sdk-python
mv oef-sdk-python oefpy
cd oefpy
sudo python3 setup.py install
python3 scripts/setup_test.py

# Build docs
cd docs
make html
cd ../..

# Install OEFCore Docker image for running nodes
get_latest fetchai oef-core
mv oef-core oefcore
cd oefcore
./oef-core-image/scripts/docker-build-img.sh
cd ..


##### SOVRIN #####

echo -e "${onyellow}Installing Sovrin...$endcolor"

# Install Hyperledger Indy
get_latest hyperledger indy-sdk
mv indy-sdk indy
if [[ "$OSTYPE" == "linux-gnu" ]]; then
    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 68DB5E88
    sudo add-apt-repository "deb https://repo.sovrin.org/sdk/deb xenial master"
    sudo apt-get update
    sudo apt-get install -y libindy
    pip3 install base58
elif [[ "$OSTYPE" == "darwin"* ]]; then
    cd indy/libindy
    ./mac.build.sh
fi

# Install Python wrapper for Hyperledger Indy and Quart
pip3 install python3-indy quart

# OEF doesn't auto-inflate
set -e
cd /usr/local/lib/python3.7/site-packages || cd /usr/local/lib/python3.7/dist-packages && yes | unzip oef-0.2.0-py3.7.egg
cd /usr/local/lib/python3.6/site-packages || cd /usr/local/lib/python3.6/dist-packages && yes | unzip oef-0.2.0-py3.6.egg

echo -e "${ongreen}ANVIL installed successfully.$endcolor"
