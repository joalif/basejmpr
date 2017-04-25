#!/usr/bin/env python2
# Author: Edward Hope-Morley (opentastic@gmail.com)
# Description: QEMU Base Image Management Utility
# Copyright (C) 2017 Edward Hope-Morley
#
# License:
#
# This file is part of basejmpr.
#
# basejmpr is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# basejmpr is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with basejmpr. If not, see <http://www.gnu.org/licenses/>.
import argparse
import os
import re
import shutil
import subprocess

from domain.utils import create_domains


def get_consumers_by_version(consumers):
    _c_by_v = {}
    for img_path in consumers:
        d = consumers[img_path]
        ver = d.get('version')
        if ver:
            entry = {'image': img_path,
                     'backing_file': d['backing_file']}
            if ver in _c_by_v:
                _c_by_v[ver].append(entry)
            else:
                _c_by_v[ver] = [entry]

    return _c_by_v


def get_consumers(root_dir, base_revs):
    consumers = {}
    for path in os.listdir(root_dir):
        newpath = os.path.join(root_dir, path)
        if os.path.isdir(newpath):
            for item in os.listdir(newpath):
                img_path = os.path.join(newpath, item)
                try:
                    info = subprocess.check_output(['qemu-img', 'info',
                                                    img_path],
                                                   stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError:
                    continue

                for line in info.split('\n'):
                    regex = r'^backing file: ([^\s]+)'
                    res = re.search(regex, line)
                    if res:
                        for rev in base_revs:
                            name = os.path.basename(res.group(1))
                            version = os.path.dirname(res.group(1))
                            version = os.path.basename(version)
                            backing_file = os.path.join(version, name)
                            for img in base_revs[rev]['files']:
                                if backing_file == os.path.join(rev, img):
                                    entry = consumers.get(img_path, {})
                                    if entry.get('version'):
                                        msg = ("Duplicate consumer entry "
                                               "detected - {}".format(
                                                   img_path))
                                        raise Exception(msg)

                                    entry['version'] = version
                                    entry['backing_file'] = backing_file
                                    consumers[img_path] = entry
                                elif img_path not in consumers:
                                    consumers[img_path] = {}

    return consumers


def create_revision(basedir, series_list, rev):
    newpath = os.path.join(basedir, rev)
    if os.path.isdir(newpath):
        raise Exception("Base revision '{}' already exists".format(rev))

    os.makedirs(newpath)
    os.makedirs(os.path.join(newpath, 'meta'))
    os.makedirs(os.path.join(newpath, 'targets'))
    try:
        for series in series_list:
            items = [{'url': ('https://cloud-images.ubuntu.com/%s/current/'
                              '%s-server-cloudimg-amd64-disk1.img' %
                              (series, series)),
                      'out': os.path.join(newpath, 'targets',
                                          '%s-server-cloudimg-amd64-disk1.img'
                                          % (series))},
                     {'url':
                      ('https://cloud-images.ubuntu.com/%s/current/'
                       'SHA256SUMS' % (series)),
                      'out': os.path.join(newpath, 'meta/SHA256SUMS')},
                     {'url': ('https://cloud-images.ubuntu.com/%s/current/'
                              '%s-server-cloudimg-amd64.manifest' %
                              (series, series)),
                      'out': os.path.join(newpath, 'meta/manifest')}]
            for item in items:
                subprocess.check_output(['wget', '-O', item['out'],
                                         item['url']])

            revs = get_revisions(basedir, rev=rev)
            with open(os.path.join(newpath, 'meta/SHA256SUMS')) as fd:
                for line in fd.readlines():
                    for target in revs[rev]['targets']:
                        if target in line:
                            link = os.path.join(newpath,
                                                line.partition(' ')[0])
                            target = os.path.join('targets', target)
                            subprocess.check_output(['chattr', '-i',
                                                     os.path.join(newpath,
                                                                  target)])
                            subprocess.check_output(['ln', '-fs',
                                                     target, link])
    except:
        shutil.rmtree(newpath)
        raise


def get_revisions(basedir, rev=None):
    revisions = {}
    if os.path.isdir(basedir) and os.listdir(basedir):
        for r in os.listdir(basedir):
            if not rev or rev == r:
                rdir = os.path.join(basedir, r)
                contents = os.listdir(rdir)
                contents1 = [c for c in contents if
                             os.path.islink(os.path.join(rdir, c))]
                contents2 = os.listdir(os.path.join(rdir, 'targets'))
                revisions[r] = {'files': contents1,
                                'targets': contents2}

    return revisions


def get_link(basedir, v, f):
    return os.path.realpath(os.path.join(basedir, v, f))


def display_info(backers_path, revisions):
    print "Available base revisions:"
    if revisions:
        for v in sorted(revisions.keys(), key=lambda k: int(k)):
            files = ['{} <- {}'.format(f, get_link(backers_path, v, f))
                     for f in revisions[v]['files']]
            print "{}:{}".format(v, ', '.join(files))
    else:
        print "-"

    consumers = get_consumers(root_path, revisions)
    print "\nConsumers:"
    c_by_rev = get_consumers_by_version(consumers)
    empty = True
    if c_by_rev:
        for rev in c_by_rev:
            if not args.revision or args.revision == rev:
                if c_by_rev[rev]:
                    for d in c_by_rev[rev]:
                        if empty:
                            backfile = os.path.basename(d['backing_file'])
                            print "{}:{}".format(rev, backfile)

                        empty = False
                        print "  -> {}".format(d['image'])

    if empty:
        print "-"

    if args.show_detached:
        print "\nDetached:"
        empty = True
        for img in consumers:
            if not consumers[img].get('version'):
                empty = False
                print "{}".format(img)

        if empty:
            print "-"

    print ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', '-p', type=str, default=None,
                        required=True, help="Path to kvm images")
    parser.add_argument('--series', '-s', type=str, default='xenial',
                        required=False, help="Ubuntu series you want "
                        "to use")
    parser.add_argument('--create-revision', action='store_true',
                        default=False, help="Whether to create a new "
                        "revision if one does not already exist. If "
                        "--revision is provided will attempt to create that "
                        "revision otherwise highest rev + 1")
    parser.add_argument('--show-detached', action='store_true', default=False,
                        help="Show qcow2 images that do not have a "
                        "revisioned backing file")
    parser.add_argument('--create-domain', action='store_true',
                        default=False, help="Create a new domain.")
    parser.add_argument('--num-domains', type=int, default=None,
                        required=False, help="Number of domains to "
                        "create. (requires --create-new-domains)")
    parser.add_argument('--domain-name-prefix', type=str, default=None,
                        required=False, help="Name to be used for new "
                        "domains created. If multiple domains are created "
                        "they will be suffixed with an integer counter.")
    parser.add_argument('--revision', '-r', type=str, default=None,
                        required=False, help="Backing file revision to "
                        "use.")
    parser.add_argument('--force', action='store_true', default=False,
                        required=False, help="Force actions such as "
                        "creating domains that already exist.")
    parser.add_argument('--domain-no-seed', action='store_true', default=False,
                        required=False, help="Do not seed new domains "
                        "with a cloud-init config-drive.")
    parser.add_argument('--domain-snaps', type=str, default=None,
                        required=False, help="Comma-delimited list of snaps "
                        "to install in domain(s) if creating new ones")
    parser.add_argument('--domain-snaps-classic', type=str, default=None,
                        required=False, help="Comma-delimited list of snaps "
                        "to install in domain(s) if creating new ones. These "
                        "snaps will be install using --classic mode")
    parser.add_argument('--domain-root-disk-size', type=str, default='40G',
                        required=False, help="Size of root disk for new "
                        "domains")
    parser.add_argument('--domain-ssh-lp-id', type=str, default='hopem',
                        required=False, help="LP user to import ssh key.")
    parser.add_argument('--domain-memory', type=int, default=1024,
                        required=False, help="Domain mem size in MB.")
    parser.add_argument('--domain-vcpus', type=int, default=1,
                        required=False, help="vCPU count.")
    parser.add_argument('--domain-boot-order', type=str, default='network,hd',
                        help="Domain boot order list (comma-seperated list of "
                             "boot devices)")
    parser.add_argument('--domain-networks', type=str, default='default',
                        help="Comma-seperated list of networks to bind domain "
                             "to. Note that these networks must already "
                             "exist.")
    args = parser.parse_args()

    root_path = os.path.realpath(args.path)
    series = [args.series] or ['trusty', 'xenial']
    backers_path = os.path.join(root_path, 'backing_files')

    if not os.path.isdir(root_path):
        raise Exception("Non-existent path '%s'" % (root_path))

    revisions = get_revisions(backers_path)

    rev = args.revision
    if rev and not revisions.get(rev) and not args.create_revision:
        raise Exception("Revision '{}' does not exist".format(rev))
    elif (not revisions or (rev and not revisions.get(rev)) or
            (args.create_revision)):
        if not revisions:
            rev = '1'
        elif not rev:
            rev = str(max([int(k) for k in revisions.keys()]) + 1)

        create_revision(backers_path, series, rev)

    # refresh
    filtered_revisions = get_revisions(backers_path, args.revision)
    display_info(backers_path, filtered_revisions)

    if args.create_domain:
        snaps = {'classic': args.domain_snaps_classic,
                 'stable': args.domain_snaps}
        revisions = get_revisions(backers_path)
        create_domains(root_path, backers_path, args.revision,
                       args.num_domains, revisions,
                       args.domain_name_prefix, args.domain_root_disk_size,
                       args.domain_ssh_lp_id, args.domain_memory,
                       args.domain_vcpus, args.domain_boot_order,
                       args.domain_networks,
                       args.force, args.domain_no_seed,
                       snap_dict=snaps)
