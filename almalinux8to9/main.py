#!/usr/bin/python3
# Copyright 1999 - 2026. WebPros International GmbH. All rights reserved.

import sys

import pleskdistup.main
import pleskdistup.registry

import cloudlinux8to9.upgrader

if __name__ == "__main__":
    pleskdistup.registry.register_upgrader(cloudlinux8to9.upgrader.CloudLinux8to9Factory())
    sys.exit(pleskdistup.main.main())
