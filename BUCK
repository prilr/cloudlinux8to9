# Copyright 1999- 2025. WebPros International GmbH. All rights reserved.
# vim:ft=python:

include_defs('//product.defs.py')


python_binary(
    name = 'cloudlinux8to9.pex',
    platform = 'py3',
    build_args = ['--python-shebang', '/usr/bin/env python3'],
    main_module = 'cloudlinux8to9.main',
    deps = [
        'dist-upgrader//pleskdistup:lib',
        '//cloudlinux8to9:lib',
    ],
)

genrule(
    name = 'cloudlinux8to9',
    srcs = [':cloudlinux8to9.pex'],
    out = 'cloudlinux8to9',
    cmd = 'cp $(location :cloudlinux8to9.pex) $OUT && chmod +x $OUT',
)
