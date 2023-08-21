import os
import argparse
import shutil
import sys
import glob
# import subprocess
import re
# import tempfile
import logging

from blackduck import Client
from bd_scan_yocto import global_values
from bd_scan_yocto import utils

parser = argparse.ArgumentParser(description='Black Duck scan Yocto project',
                                 prog='bd_scan_yocto')

# parser.add_argument("projfolder", nargs="?", help="Yocto project folder to analyse", default=".")

parser.add_argument("--blackduck_url", type=str, help="Black Duck server URL (REQUIRED)", default="")
parser.add_argument("--blackduck_api_token", type=str, help="Black Duck API token (REQUIRED)", default="")
parser.add_argument("--blackduck_trust_cert", help="Black Duck trust server cert", action='store_true')
parser.add_argument("--detect-jar-path", help="Synopsys Detect jar path", default="")
parser.add_argument("-p", "--project", help="Black Duck project to create (REQUIRED)", default="")
parser.add_argument("-v", "--version", help="Black Duck project version to create (REQUIRED)", default="")
parser.add_argument("--oe_build_env",
                    help="Yocto build environment config file (default 'oe-init-build-env')",
                    default="oe-init-build-env")
parser.add_argument("-t", "--target", help="Yocto target (default 'core-image-sato') (REQUIRED)",
                    default="core-image-sato")
parser.add_argument("-m", "--manifest",
                    help="Built license.manifest file)",
                    default="")
parser.add_argument("--machine", help="Machine Architecture (for example 'qemux86_64')",
                    default="qemux86_64")
parser.add_argument("--skip_detect_for_bitbake", help="Skip running Detect for Bitbake dependencies",
                    action='store_true')
parser.add_argument("--detect_opts", help="Additional Synopsys Detect options", default="")
parser.add_argument("--cve_check_only", help="Only check for patched CVEs from cve_check and update existing project "
                                             "(skipping scans)",
                    action='store_true')
parser.add_argument("--no_cve_check", help="Skip checking/updating patched CVEs", action='store_true')
parser.add_argument("--cve_check_file",
                    help="CVE check output file (if not specified will be determined from environment)", default="")
parser.add_argument("--wizard", help="Start command line wizard (Wizard will run by default if config incomplete)",
                    action='store_true')
parser.add_argument("--nowizard", help="Do not use wizard (command line batch only)", action='store_true')
parser.add_argument("--extended_scan_layers",
                    help="Specify a comma-delimited list of layers where packages within recipes will be expanded "
                         "and Snippet scanned",
                    default="")
parser.add_argument("--snippets", help="Run snippet scan for downloaded package files",
                    action='store_true')
parser.add_argument("--exclude_layers",
                    help="Specify a command-delimited list of layers where packages within recipes will not be "
                         "Signature scanned", default="")
parser.add_argument("--download_dir",
                    help="Download directory where original packages are downloaded (usually poky/build/downloads)",
                    default="")
parser.add_argument("--rpm_dir",
                    help="Download directory where rpm packages are downloaded "
                         "(usually poky/build/tmp/deploy/rpm/<ARCH>)",
                    default="")
parser.add_argument("--testmode", help="Test mode - skip various checks", action='store_true')
parser.add_argument("--debug", help="Debug logging mode", action='store_true')
args = parser.parse_args()

if args.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


def check_args():
    # if platform.system() != "Linux":
    #     print('''Please use this program on a Linux platform or extract data from a Yocto build then
    #     use the --bblayers_out option to scan on other platforms\nExiting''')
    #     sys.exit(2)

    if args.oe_build_env != '':
        global_values.oe_build_env = args.oe_build_env

    if args.debug:
        global_values.debug = True

    if args.testmode:
        global_values.testmode = True
    else:
        if not os.path.isfile(global_values.oe_build_env):
            logging.error(f"Cannot find Yocto build environment config file '{global_values.oe_build_env}'")
            sys.exit(2)

        # if os.system(f"source {global_values.oe_build_env}; bitbake --help >/dev/null")
        # # if shutil.which("bitbake") is None:
        #     print("ERROR: Yocto environment not set (run 'source oe-init-build-env')")
        #     sys.exit(2)

        if shutil.which("java") is None:
            logging.error("Java runtime is required and should be on the PATH")
            sys.exit(2)

    url = os.environ.get('BLACKDUCK_URL')
    if args.blackduck_url != '':
        global_values.bd_url = args.blackduck_url
    elif url is not None:
        global_values.bd_url = url
    else:
        logging.warning("Black Duck URL not specified")

    if args.project != "" and args.version != "":
        global_values.bd_project = args.project
        global_values.bd_version = args.version
    else:
        logging.warning("Black Duck project/version not specified")

    api = os.environ.get('BLACKDUCK_API_TOKEN')
    if args.blackduck_api_token != '':
        global_values.bd_api = args.blackduck_api_token
    elif api is not None:
        global_values.bd_api = api
    else:
        logging.warning("Black Duck API Token not specified")

    trustcert = os.environ.get('BLACKDUCK_TRUST_CERT')
    if trustcert == 'true' or args.blackduck_trust_cert:
        global_values.bd_trustcert = True

    if args.download_dir != '':
        if not os.path.isdir(args.download_dir):
            logging.warning(f"Specified download package folder '{args.download_dir}' does not exist")
        else:
            global_values.download_dir = os.path.abspath(args.download_dir)

    if args.rpm_dir != '':
        if not os.path.isdir(args.rpm_dir):
            logging.warning(f"Specified download rpm folder '{args.rpm_dir}' does not exist")
        else:
            global_values.rpm_dir = os.path.abspath(args.rpm_dir)

    if args.cve_check_only or args.cve_check_file != '':
        global_values.cve_check = True

    if args.cve_check_file != "":
        if args.no_cve_check:
            logging.error("Options cve_check_file and no_cve_check cannot be specified together")
            sys.exit(2)

        if not os.path.isfile(args.cve_check_file):
            logging.warning(f"CVE check output file '{args.cve_check_file}' does not exist")
        else:
            global_values.cve_check_file = args.cve_check_file

    if args.cve_check_only and args.no_cve_check:
        logging.error("Options --cve_check_only and --no_cve_check cannot be specified together")
        sys.exit(2)

    if args.manifest != "":
        if not os.path.isfile(args.manifest):
            logging.warning(f"Manifest file '{args.manifest}' does not exist")
        else:
            global_values.manifest_file = args.manifest

    if args.machine != "":
        global_values.machine = args.machine

    if args.detect_jar_path != "" and not os.path.isfile(args.detect_jar_path):
        logging.error(f"Detect jar file {args.detect_jar_path} does not exist")
        sys.exit(2)
    else:
        global_values.detect_jar = args.detect_jar_path

    # if args.report != "":
    #     global_values.report_file = args.report

    if args.target != "":
        global_values.target = args.target

    if args.skip_detect_for_bitbake:
        global_values.skip_detect_for_bitbake = True

    if args.extended_scan_layers != '':
        global_values.extended_scan_layers = args.extended_scan_layers.split(',')

    if args.exclude_layers != '':
        global_values.exclude_layers = args.exclude_layers.split(',')

    if args.detect_opts != '':
        global_values.detect_opts = args.detect_opts

    if args.snippets:
        global_values.snippets = True

    # if args.bblayers_out != "":
    #     if args.extended_scan_layers:
    #         print(f"INFO: Bitbake-layers output file {args.bblayers_out} is not required unless "
    #               "--extended_scan_layers is specified")
    #     if os.path.isfile(args.bblayers_out):
    #         global_values.bblayers_file = args.bblayers_out
    #     else:
    #         print(f"WARNING: bitbake-layers output file {args.bblayers_out} does not exist - skipping ...")

    return


def connect():
    if global_values.bd_url == '':
        return None

    bd = Client(
        token=global_values.bd_api,
        base_url=global_values.bd_url,
        timeout=30,
        verify=global_values.bd_trustcert  # TLS certificate verification
    )
    try:
        bd.list_resources()
    except Exception as exc:
        logging.warning(f'Unable to connect to Black Duck server - {str(exc)}')
        return None

    logging.info(f'Connected to Black Duck server {global_values.bd_url}')
    return bd


def get_bitbake_env():
    if not global_values.testmode:
        logging.info("GETTING YOCTO ENVIRONMENT")
        logging.info("- Running 'bitbake -e' ...")

        cmd = f"bash -c 'source {global_values.oe_build_env}; bitbake -e'"
        ret = utils.run_cmd(cmd)
        if ret == b'':
            logging.error("Cannot run 'bitbake -e'")
            sys.exit(2)
        # output = subprocess.check_output(['bitbake', '-e'], stderr=subprocess.STDOUT)
        # mystr = output.decode("utf-8").strip()
        lines = ret.decode("utf-8").split('\n')

        rpm_dir = ''
        ipk_dir = ''
        for mline in lines:
            if re.search(
                    "^(MANIFEST_FILE|DEPLOY_DIR|MACHINE_ARCH|DL_DIR|DEPLOY_DIR_RPM|DEPLOY_DIR_IPK|IMAGE_PKGTYPE)=",
                    mline):

                # if re.search('^TMPDIR=', mline):
                #     tmpdir = mline.split('=')[1]
                val = mline.split('=')[1].strip('\"')
                if global_values.manifest_file == '' and re.search('^MANIFEST_FILE=', mline):
                    global_values.manifest = val
                    logging.info(f"Bitbake Env: manifestfile={global_values.manifest_file}")
                elif global_values.deploy_dir == '' and re.search('^DEPLOY_DIR=', mline):
                    global_values.deploy_dir = val
                    logging.info(f"Bitbake Env: deploydir={global_values.deploy_dir}")
                elif global_values.machine == '' and re.search('^MACHINE_ARCH=', mline):
                    global_values.machine = val
                    logging.info(f"Bitbake Env: machine={global_values.machine}")
                elif global_values.download_dir == '' and re.search('^DL_DIR=', mline):
                    global_values.download_dir = val
                    logging.info(f"Bitbake Env: download_dir={global_values.download_dir}")
                elif rpm_dir == '' and re.search('^DEPLOY_DIR_RPM=', mline):
                    rpm_dir = val
                    logging.info(f"Bitbake Env: rpm_dir={rpm_dir}")
                elif ipk_dir == '' and re.search('^DEPLOY_DIR_IPK=', mline):
                    ipk_dir = val
                    logging.info(f"Bitbake Env: ipk_dir={ipk_dir}")
                elif re.search('^IMAGE_PKGTYPE=', mline):
                    global_values.image_pkgtype = val
                    logging.info(f"Bitbake Env: image_pkgtype={global_values.image_pkgtype}")

        if global_values.image_pkgtype == 'rpm' and rpm_dir != '':
            global_values.pkg_dir = rpm_dir
        elif global_values.image_pkgtype == 'ipk' and ipk_dir != '':
            global_values.pkg_dir = ipk_dir


def find_yocto_files():
    machine = global_values.machine.replace('_', '-')

    if global_values.manifest_file == "":
        if global_values.target == '':
            logging.warning("Manifest file not specified and it could not be determined as Target not specified")
        else:
            manpath = os.path.join(global_values.deploy_dir, "licenses",
                                   f"{global_values.target}-{machine}-*", "license.manifest")
            manifest = ""
            manlist = glob.glob(manpath)
            if len(manlist) > 0:
                manifest = manlist[-1]

            if not os.path.isfile(manifest):
                logging.warning(f"Manifest file '{manifest}' could not be located")
            else:
                logging.info(f"Located license.manifest file {manifest}")
                global_values.manifest_file = manifest

    if global_values.cve_check_file == '':
        if global_values.target == '':
            logging.warning("CVE check file not specified and it could not be determined as Target not specified")
        else:
            imgdir = os.path.join(global_values.deploy_dir, "images", machine)
            cvefile = ""
            for file in sorted(os.listdir(imgdir)):
                if file.startswith(global_values.target + "-" + machine + "-") and \
                        file.endswith('rootfs.cve'):
                    cvefile = os.path.join(imgdir, file)

            if not os.path.isfile(cvefile):
                logging.warning(f"CVE check file {cvefile} could not be located")
            else:
                logging.info(f"Located CVE check output file {cvefile}")
                global_values.cve_check_file = cvefile
                global_values.cve_check = True

    return


def input_number(prompt):
    print(f'{prompt} (q to quit): ', end='')
    val = input()
    while not val.isnumeric() and val.lower() != 'q':
        print('Please enter a number (or q)')
        print(f'{prompt}: ', end='')
        val = input()
    if val.lower() != 'q':
        return int(val)
    else:
        logging.info('Terminating')
        sys.exit(2)


def input_file(prompt, accept_null, file_exists):
    if accept_null:
        prompt_help = '(q to quit, Enter to skip)'
    else:
        prompt_help = '(q to quit)'
    print(f'{prompt} {prompt_help}: ', end='')
    val = input()
    while (file_exists and not os.path.isfile(val)) and val.lower() != 'q':
        if accept_null and val == '':
            break
        print(f'Invalid input ("{val}" is not a file)')
        print(f'{prompt} {prompt_help}: ', end='')
        val = input()
    if val.lower() != 'q' or (accept_null and val == ''):
        return val
    else:
        logging.info('Terminating')
        sys.exit(2)


def input_folder(prompt):
    prompt_help = '(q to quit)'
    print(f'{prompt} {prompt_help}: ', end='')
    val = input()
    while not os.path.isdir(val) and val.lower() != 'q':
        if val == '':
            break
        print(f'Invalid input ("{val}" is not a folder)')
        print(f'{prompt} {prompt_help}: ', end='')
        val = input()
    if val.lower() != 'q':
        return val
    else:
        logging.info('Terminating')
        sys.exit(2)


def input_string(prompt):
    print(f'{prompt} (q to quit): ', end='')
    val = input()
    while len(val) == 0 and val != 'q':
        print(f'{prompt}: ', end='')
        val = input()
    if val.lower() != 'q':
        return val
    else:
        logging.info('Terminating')
        sys.exit(2)


def input_string_default(prompt, default):
    print(f"{prompt} [Press return for '{default}'] (q to quit): ", end='')
    val = input()
    if val.lower() == 'q':
        sys.exit(2)
    if len(val) == 0:
        logging.info('Terminating')
        return default
    else:
        return val


def input_yesno(prompt):
    accept_other = ['n', 'q', 'no', 'quit']
    accept_yes = ['y', 'yes']

    print(f'{prompt} (y/n/q): ', end='')
    val = input()
    while val.lower() not in accept_yes and val.lower() not in accept_other:
        print('Please enter y or n')
        print(f'{prompt}: ', end='')
        val = input()
    if val.lower() == 'q':
        sys.exit(2)
    if val.lower() in accept_yes:
        return True
    return False


def input_filepattern(pattern, filedesc, path):
    retval = ''
    enterfile = False
    if input_yesno(f"Do you want to search recursively for '{filedesc}'?"):
        files_list = glob.glob(os.path.join(path, pattern), recursive=True)
        if len(files_list) > 0:
            print(f'Please select the {filedesc} file to be used: ')
            files_list = ['None of the below'] + files_list
            for i, f in enumerate(files_list):
                print(f'\t{i}: {f}')
            val = input_number('Please enter file entry number')
            if val == 0:
                enterfile = True
            else:
                retval = files_list[val]
        else:
            print(f'Unable to find {filedesc} ...')
            enterfile = True
    else:
        enterfile = True

    if enterfile:
        retval = input_file(f'Please enter the {filedesc} path', False, True)

    if not os.path.isfile(retval):
        logging.error(f'Unable to locate {filedesc} - exiting')
        sys.exit(2)
    return retval


def do_wizard():
    print('\nRUNNING WIZARD (Use --no_wizard to disable) ...')

    wiz_dict = [
        {'value': 'global_values.bd_url', 'prompt': 'Black Duck server URL', 'vtype': 'string'},
        {'value': 'global_values.bd_api', 'prompt': 'Black Duck API token', 'vtype': 'string'},
        {'value': 'global_values.bd_trustcert', 'prompt': 'Trust BD Server certificate', 'vtype': 'yesno'},
        {'value': 'global_values.bd_project', 'prompt': 'Black Duck project name', 'vtype': 'string'},
        {'value': 'global_values.bd_version', 'prompt': 'Black Duck version name', 'vtype': 'string'},
        {'value': 'global_values.manifest_file', 'prompt': 'Manifest file path', 'vtype': 'file_pattern',
         'pattern': 'license.manifest', 'filedesc': 'license.manifest file',
         'searchpath': 'global_values.deploy_dir'},
        {'value': 'global_values.target', 'prompt': 'Yocto target name', 'vtype': 'string',
         'condition': 'global_values.skip_detect_for_bitbake'},
        # {'value': 'global_values.deploy_dir', 'prompt': 'Yocto deploy folder', 'vtype': 'folder'},
        {'value': 'global_values.download_dir', 'prompt': 'Yocto package download folder', 'vtype': 'folder'},
        {'value': 'global_values.rpm_dir', 'prompt': 'Yocto rpm package download folder', 'vtype': 'folder'},
        # {'value': 'global_values.cve_check',
        #  'prompt': 'Do you want to run a CVE check to patch CVEs in the BD project which have been patched locally?',
        #  'vtype': 'yesno'},
        # {'value': 'global_values.cve_check_file', 'prompt': 'CVE check file path',
        #  'vtype': 'file_pattern', 'pattern': '**/rootfs.cve', 'filename': 'CVE check output file',
        #  'condition': 'global_values.cve_check'},
        # {'value': 'global_values.report_file', 'prompt': 'Output report file', 'vtype': 'string'},
    ]

    wiz_count = 0
    for wiz_entry in wiz_dict:
        val = ''
        existingval = eval(wiz_entry['value'])
        if existingval == '':
            if 'condition' in wiz_entry:
                conditionval = eval(wiz_entry['condition'])
                if conditionval:
                    continue
            if wiz_entry['vtype'] == 'string':
                val = input_string(wiz_entry['prompt'])
            elif wiz_entry['vtype'] == 'string_default':
                val = input_string_default(wiz_entry['prompt'], wiz_entry['default'])
            elif wiz_entry['vtype'] == 'yesno':
                val = input_yesno(wiz_entry['prompt'])
            elif wiz_entry['vtype'] == 'file':
                val = input_file(wiz_entry['prompt'], False, True)
            elif wiz_entry['vtype'] == 'folder':
                val = input_folder(wiz_entry['prompt'])
            elif wiz_entry['vtype'] == 'file_pattern':
                val = input_filepattern(wiz_entry['pattern'], wiz_entry['filedesc'], eval(wiz_entry['searchpath']))
            wiz_count += 1
            globals()[wiz_entry['value']] = val
            logging.debug(f"{wiz_entry['value']}={val}")

    if wiz_count == 0:
        print("- Nothing for Wizard to do - continuing ...\n")
    return
