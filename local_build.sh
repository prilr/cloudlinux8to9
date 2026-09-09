#!/bin/bash
# Sample script to build cloudlinux8to9 using prebuilt buck

# download the prebuilt buck pex latest version
# wget https://jitpack.io/com/github/facebook/buck/2022.05.05.01/buck-2022.05.05.01.pex -O /root/buck-2022.05.05.01.pex

# make a local build of cloudlinux8to9 via prebuilt buck pex
# assuming the cloudlinux8to9 is cloned in /root/cloudlinux8to9
cd /root/cloudlinux8to9 || exit
/root/buck-2022.05.05.01.pex build :cloudlinux8to9
