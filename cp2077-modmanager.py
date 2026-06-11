#!/usr/bin/env python

'''
'''

# Python imports
import os, sys, pathlib, argparse, zipfile, json, re, shutil, time
from datetime import datetime, timezone
# External imports
import py7zr
import rarfile
import requests
from tqdm import tqdm
#import pefile

# Functions and classes
class Utils:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def printf(self, *vars):
        toPrint = vars[0]
        if not toPrint:
            raise Exception("utils.printf: cannot print a None value")
            return
        for i in range(0, len(vars)-1):
            value = vars[i+1]
            if type(value) != type(''):
                value = str(value)
            toPrint = toPrint.replace('{'+str(i)+'}', value)
        print(toPrint)

    def verbosePrint(self, *vars):
        if self.verbose: self.printf(*vars)

    def json_pretty(self, data, indent=2):
        return json.dumps(data, indent=indent)

    def json_print(self, data, indent=2):
        print(self.json_pretty(data, indent))

    def json_save_file(self, path, data, indent=None):
        with open (path, 'w') as f:
            json.dump(data, f, indent=indent)

    def compareMN(self, mn, data):
        if len(mn) == 0 or len(data) == 0:
            return False
        for i in range(0, len(mn)):
            if mn[i] != data[i]:
                return False
        return True

    def isCP2077(self, path):
        exe = os.path.join(path, 'bin/x64/Cyberpunk2077.exe')
        if not os.path.exists(exe):
            return False
        elif not os.path.isfile(exe):
            return False
        else:
            return True

    def backupFile(self, path, dest=None):
        if not os.path.exists(path): 
            self.printf('[X] Cannot backup database, file does not exist -> {0}', path)
            return False
        file = os.path.basename(path) + ".backup" + datetime.today().strftime('%Y%m%d%H%M%S')
        if dest:
            dest = os.path.join(dest, file)
        else:
            dest = file
        shutil.copyfile(path, dest)
        self.verbosePrint('[i] Backed up database from {0} to {1}', path, dest)
        return True

    def yesno(self, message):
        while True:
            q = input(message + ' (answer with yes or no) -> ')
            if q == 'yes': return True
            elif q == 'no': return False
            else: continue

class NexusMods:
    # API 3.0.0 -> https://api-docs.nexusmods.com
    # Legacy v1 API -> https://app.swaggerhub.com/apis-docs/NexusMods/nexus-mods_public_api_params_in_form_data/1.0#/
    def __init__(self, utils, api_key, game_domain):
        self.utils = utils
        self.api_key = api_key
        self.game_domain = game_domain
        self.request_endpoint = 'https://api.nexusmods.com/v1'
        self.request_headers = { 'apikey': self.api_key }
        self.ready = self.checks()

    def requests_get(self, uri):
        r = requests.get(uri, headers=self.request_headers)
        time.sleep(0.25)
        if r.status_code == 200:
            self.utils.verbosePrint('[*] [nexusmods] Get request 200 -> uri={0}', uri)
            return r.json()
        else:
            self.utils.printf('[!] [nexusmods] HTTP GET request failed:')
            self.utils.printf('      status_code -> {0}', r.status_code)
            self.utils.printf('      reason -> {0}', r.reason)
            self.utils.printf('      uri -> {0}', uri)
            return False

    def checks(self):
        if not self.api_key:
            print("[!][nexusmods] No api key provided.")
            return False
        elif not self.mod_get(2380): # red4ext id
            print("[X][nexusmods] Failed to read red4ext mod, NexusMods API won't be used")
            return False
        else:
            return True

    def mod_files(self, mod_id):
        if not mod_id: return
        if not type(mod_id) == str: mod_id = str(mod_id)
        uri = self.request_endpoint + '/games/' + self.game_domain + '/mods/' + mod_id + '/files.json'
        return self.requests_get(uri)

    def mod_get(self, mod_id):
        if not mod_id: return
        if not type(mod_id) == str: mod_id = str(mod_id)
        uri = self.request_endpoint + '/games/' + self.game_domain + '/mods/' + mod_id + ".json"
        return self.requests_get(uri)

class Database:
    def __init__(self, utils, database_path, database_backups_path, nexus=None):
        self.utils = utils
        self.path = self.create(database_path)
        self.backups_path = database_backups_path
        self.was_backed_up = False
        self.data = None
        self.dataLength = None
        self.date_format = '%Y-%m-%d %H:%M:%S'
        self.nexus = nexus
        self.load()

    def list_installed_mods(self):
        i = 1
        for m in self.data['mods']:
            if 'NexusMods' in m and 'name' in m['NexusMods']:
                name = m['NexusMods']['name']
            else:
                name = None
            text = str.format('[{0}][{1}][{2}] {3} -> {4}', str(i), m['InstallDate'], m['File']['NexusModId'], m['File']['Name'], name)
            self.utils.printf(text)
            i = i + 1

    def show_info(self):
        # Mods unidentified
        mods_no_nexus = []
        for m in self.data['mods']: 
            if not m['File']['NexusModId'] or not m['NexusMods']: mods_no_nexus.append(m)
        if len(mods_no_nexus) == 1: tmp = 'mod'
        else: tmp = 'mods'
        self.utils.printf('[i] {0} unidentified {1} (without nexusmods mod_id):', len(mods_no_nexus), tmp)
        self.utils.json_print(mods_no_nexus)
        # Last installed mod
        last_installed = self.data['mods'][self.dataLength-1]
        print('[i] Last installed mod:')
        self.utils.json_print(last_installed)

    def create(self, database_path):
        if not os.path.exists(database_path): self.utils.json_save_file(database_path, { 'mods': [] })
        return database_path

    def backup(self):
        if not self.was_backed_up: 
            self.utils.backupFile(self.path, self.backups_path)
            self.was_backed_up = True

    def load(self):
        with open(self.path, 'r') as f:
            self.data = json.load(f)
            self.dataLength = len(self.data['mods'])
        self.utils.verbosePrint('[i] Loaded database from path "{0}"', self.path)
        self.utils.printf('[i] {0} mods in database', self.dataLength)

    def save(self):
        self.utils.json_save_file(self.path, self.data)

    def parse_mod(self, mod):
        file = os.path.basename(mod)
        mod_data = {
            'InstallDate': datetime.today().strftime(self.date_format),
            'InstallDate_UTC_0': datetime.now(timezone.utc).strftime(self.date_format),
            'File': {
                'Name': file,
                'Version': None,
                'NexusModId': None,
                'NexusUploadedTimeStamp': None
            },
            'NexusMods': {}
        }
        # Extract data from filename
        r_modid = re.search(r'-(\d+)-', file)
        r_fileid = re.search(r'-(\d{10})\.', file)
        if r_modid:     mod_data['File']['NexusModId'] = r_modid.groups()[0]
        if r_fileid:    mod_data['File']['NexusUploadedTimeStamp'] = r_fileid.groups()[0]
        if mod_data['File']['NexusModId'] and mod_data['File']['NexusUploadedTimeStamp']:
            tmp = file.replace(mod_data['File']['NexusModId'], '+').replace(mod_data['File']['NexusUploadedTimeStamp'], '+')
            r_version = re.search(r'-([0-9-]+)-', tmp)
            if r_version: mod_data['File']['Version'] = r_version.groups()[0].replace('-', '.')
        return mod_data

    def is_installed(self, mod):
        mod_data = self.parse_mod(mod)
        if mod_data['File']['NexusModId']:
            for m in self.data['mods']:
                if  (m['File']['Name']                   == mod_data['File']['Name']) and \
                    (m['File']['NexusModId']             == mod_data['File']['NexusModId']) and \
                    (m['File']['NexusUploadedTimeStamp'] == mod_data['File']['NexusUploadedTimeStamp']):
                    return True
        else:
            for m in self.data['mods']:
                if m['File']['Name'] == mod_data['File']['Name']:
                    return True
        return False

    def add_mod(self, mod):
        mod_data = self.parse_mod(mod)
        # Query nexusmods for mod info
        if self.nexus and self.nexus.ready:
            nm_mod = self.nexus.mod_get(mod_data['File']['NexusModId'])
            if nm_mod:
                # Borrar descripción del mod. No la necesitamos y ocupa mucho espacio.
                del nm_mod['description']
                # Guardar info del mod
                mod_data['NexusMods'] = nm_mod
        self.data['mods'].append(mod_data)
        self.save()

    def remove_mod(self, mod):
        mod_data = self.parse_mod(mod)
        for i in range(0, len(self.data['mods'])):
            if  (self.data['mods'][i]['File']['Name']                   == mod_data['File']['Name']) and \
                (self.data['mods'][i]['File']['NexusModId']             == mod_data['File']['NexusModId']) and \
                (self.data['mods'][i]['File']['NexusUploadedTimeStamp'] == mod_data['File']['NexusUploadedTimeStamp']):
                self.data['mods'].pop(i)
                self.save()
                return
        self.utils.printf('[X] Mod not in database -> {0}', mod_data['File']['Name'])

class Archive:
    def __init__(self, utils, path):
        if not path:
            raise Exception("Archive.init: Path is null"); return
        elif not os.path.exists(path):
            raise Exception(str.format("Archive.init: path {0} does not exist", path)); return
        elif not os.path.isfile(path):
            raise Exception(str.format('Archive.init: path {0} is not a file', path)); return
        else:
            self.path = path
            self.utils = utils
            self.format = self.getFileFormat() # 7z, zip or rar

    def getFileFormat(self):
        MN_7zip = [ 0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C ]
        MN_zip  = [ 0x50, 0x4B ]
        MN_rar  = [ 0x52, 0x61, 0x72, 0x21, 0x1A, 0x07 ]
        with open(self.path, 'rb') as f:
            data = f.read(10); f.close()
            if   self.utils.compareMN(MN_7zip, data): return '7z'
            elif self.utils.compareMN(MN_rar, data):  return 'rar'
            elif self.utils.compareMN(MN_zip, data):  return 'zip'
            else: raise Exception(str.format('Archive.getFileFormat: unsupported format or corrupted file -> {0}', self.path))

    def extract(self, destination):
        if self.format == 'zip':
            f = zipfile.ZipFile(self.path, 'r')
            f.extractall(destination)
        elif self.format == '7z':
            f = py7zr.SevenZipFile(self.path, 'r')
            f.extractall(destination)
        elif self.format == 'rar':
            f = rarfile.RarFile(self.path, 'r')
            f.extractall(destination)
        else: raise Exception('Archive.extract: Unsupported archive format')

    def read(self):
        if self.format == 'zip':
            r = []; z = zipfile.ZipFile(self.path, 'r')
            for f in z.filelist:
                if f.file_size > 0: r.append(f.filename)
            return r
        elif self.format == '7z':
            r = []; sz = py7zr.SevenZipFile(self.path, 'r')
            for f in sz.files:
                if not f.emptystream:
                    r.append(f.filename)
            return r
        elif self.format == 'rar':
            r = []; rar = rarfile.RarFile(self.path, 'r')
            for f in rar.namelist():
                if not f[len(f)-1] == '/':
                    r.append(f)
            return r
        else: raise Exception('Archive.extract: Unsupported archive format')

class ModManager:
    def __init__(self, utils, database_path, database_backups_path, cp2077_path, nm_api_key=None, simulation_mode=False):
        self.cp2077_path = cp2077_path
        self.nexus = NexusMods(utils, nm_api_key, 'cyberpunk2077')
        self.database = Database(utils, database_path, database_backups_path, self.nexus)
        self.utils = utils
        self.simulation_mode = simulation_mode

    def reload_database(self):
        self.database = Database(self.utils, self.database.path, self.database.backups_path)

    def check_mod_path(self, path):
        if not os.path.exists(path):
            self.utils.printf('[X] Path does not exist -> {0}', path)
            return False
        return True
        
    def check_archive_valid_path(self, archive):
        file_list = archive.read()
        check_for = [ 'archive', 'bin', 'engine', 'r6', 'red4ext' ]
        for f in file_list:
            a = f.split('/')[0]
            if a in check_for:
                return True
        return False

    def check_archive_files_installed(self, archive):
        file_list = archive.read()
        found_files = []
        for f in file_list:
            if f.endswith('.txt'): continue
            p = os.path.join(self.cp2077_path, f)
            if os.path.exists(p): found_files.append(f)
        return found_files

    def check_mod_updates(self):
        self.utils.printf('[+] Looking for mod updates...')
        c = 0  # contador
        results = [] # resultado
        for m in tqdm(self.database.data['mods']):
            # Si no tiene la info de nexusmods se salta
            if m == None or not 'NexusMods' in m or not 'mod_id' in m['NexusMods']: continue
            # Leer mod files desde nexus
            mod_id = m['NexusMods']['mod_id']
            mod_files = self.nexus.mod_files(mod_id)
            if not mod_files:
                self.utils.printf('[X] Failed to get mod files for mod id {0}', mod_id)
                continue
            # Sacar último fichero subido
            installed_file_name = m['File']['Name']
            last_file_name = installed_file_name
            last_file = None
            for i in mod_files['file_updates']:
                if i['old_file_name'] == last_file_name:
                    last_file_name = i['new_file_name']
                    last_file = i
            # Comprobar con el fichero instalado actualmente
            if not installed_file_name == last_file_name:
                c = c + 1
                mod_name = m['NexusMods']['name']
                self.utils.printf('[-] Found update for mod {0} - {1}', mod_id, mod_name)
                # Add to results
                r = {
                    'id': str(mod_id),
                    'name': mod_name,
                    'installed_file_name': installed_file_name,
                    'last_file_name': last_file_name
                }
                results.append(r)
        # Cuántos mods tienen actualizaciones y guardar resultados
        self.utils.printf('[-] {0} mods have updates', str(c))
        if c > 0:
            results_path = '/tmp/mod_updates.json'
            self.utils.json_save_file(results_path, results, 2)
            self.utils.printf('[-] Results written to file {0}', results_path)
        return True

    def install_mod(self, archive):
        # Skip .disabled mods
        if archive.path.endswith('.disabled'):
            self.utils.verbosePrint('[i] Skipping disabled file {0}', archive.path)
            return False
        # Check if archive paths are valid
        if not self.check_archive_valid_path(archive):
            self.utils.printf('[!] Mod cannot be installed. Archive does not match any known parent mod folder. -> {0}', archive.path)
            return False
        # Check if mod is in database
        elif self.database.is_installed(archive.path):
            self.utils.verbosePrint('[!] Mod is in database, installation skipped -> {0}', archive.path)
            return False
        # Backup database before installing
        if not self.simulation_mode: self.database.backup()
        # Install mod
        self.utils.printf('[+] Installing mod "{0}"', archive.path)
        if not self.simulation_mode:
            # Check if mod files are already installed
            already_installed = self.check_archive_files_installed(archive)
            if already_installed:
                print('    [!] Some mod files are already installed:')
                for f in already_installed: self.utils.printf('        - {0}', f)
                if not self.utils.yesno('        Do you want to continue and replace files? (mod will still be added to the database)'):
                    print('    [i] Mod installation skipped')
                    return False
            # Perform install
            archive.extract(self.cp2077_path)
            self.database.add_mod(archive.path)
            print('    [-] Added entry to database')
        return True

    def install(self, path):
        # Check mod path
        if not self.check_mod_path(path): return
        # If file single
        if os.path.isfile(path):
            # Do install
            self.install_mod(Archive(self.utils, path))
        # If dir multiple
        else:
            number_installed = 0
            number_skipped = 0
            # For every element in path
            for i in pathlib.Path(path).rglob( '*' ):
                # If is file
                if os.path.isfile(i._raw_path):
                    # Do install
                    if self.install_mod(Archive(self.utils, i._raw_path)): number_installed = number_installed + 1
                    else: number_skipped = number_skipped + 1
            self.utils.printf("[i] {0} new mods installed", number_installed)
            self.utils.printf("[i] {0} mods skipped", number_skipped)

    def uninstall_mod(self, archive, delete_archive):
        # Skip .disabled mods
        if archive.path.endswith('.disabled'):
            self.utils.verbosePrint('[i] Skipping disabled file {0}', archive.path)
            return False
        is_in_db = self.database.is_installed(archive.path)
        # Check if mod archive has valid paths
        if not self.check_archive_valid_path(archive):
            self.utils.printf('[!] Mod cannot be uninstalled. Archive does not match any known parent mod folder. -> {0}', archive.path)
            return False
        # Check if mod is in database
        elif not is_in_db:
            self.utils.printf('[!] Mod is not in database -> {0}', archive.path)
            if not self.utils.yesno('    Do you want to continue anyway?'):
                print('   [i] Uninstall procedure skipped')
                return False
        # Backup database before uninstall
        if not self.simulation_mode and is_in_db: self.database.backup()
        # Uninstall
        self.utils.printf('[+] Uninstalling mod "{0}"', archive.path)
        for f in archive.read():
            fp = os.path.join(self.cp2077_path, f)
            if os.path.exists(fp): 
                if not self.simulation_mode: 
                    os.remove(fp)
                    self.utils.verbosePrint('    [-] Deleted file -> {0}', fp)
            else:
                self.utils.verbosePrint('    [-] File does not exist -> {0}', fp)
        if not self.simulation_mode and is_in_db:
            self.database.remove_mod(archive.path)
            print('    [-] Removed entry from database')
        if not self.simulation_mode and delete_archive:
            os.remove(archive.path)
            self.utils.printf('    [-] Deleted mod archive -> {0}', archive.path)
        return True

    def uninstall(self, path, delete_archive):
        # Check mod path
        if not self.check_mod_path(path): return
        # If file single
        if os.path.isfile(path):
            self.uninstall_mod(Archive(self.utils, path), delete_archive)
        # If dir multiple
        else:
            if not self.utils.yesno('    Multiple mods will be uninstalled, Are you sure to continue?'):
                print("    [i] Uninstall operation canceled.")
                return
            number_uninstalled = 0
            number_skipped = 0
            for i in pathlib.Path(path).rglob( '*' ):      
                if os.path.isfile(i._raw_path):
                    if self.uninstall_mod(Archive(self.utils, i._raw_path), delete_archive): number_uninstalled = number_uninstalled + 1
                    else: number_skipped = number_skipped + 1
            self.utils.printf("[i] {0} mods uninstalled", number_uninstalled)
            self.utils.printf("[i] {0} mods skipped", number_skipped)

    def reset(self, backup_path):
        # Check file backup path
        if not (backup_path and os.path.exists(backup_path)):
            raise Exception(str.format('Backup path does not exist -> "{0}"', backup_path))
        # Init vars
        self.utils.printf('[!] Reset action started for backup "{0}"', backup_path)
        archive = Archive(self.utils, backup_path)
        result_files_log = '/tmp/result_files.log'
        files_in_backup = archive.read()
        # Delete files not in backup aka mod files
        # https://csatlas.com/python-list-directory/#recursive
        result_files = { 'delete': [], 'keep': [] }
        # Need relative path instead of absolute to check against the archive
        to_replace = self.cp2077_path.split("/")
        to_replace.pop(0)
        to_replace.pop(len(to_replace)-1)
        to_replace = '/' + '/'.join(to_replace) + '/'
        for i in pathlib.Path(self.cp2077_path).rglob( '*' ):
            if not os.path.isfile(i._raw_path):
                continue
            f = i._raw_path.replace(to_replace, '')
            # Skip mod configuration and log files:
            #   - Files with .log extension.
            #   - ACU character .preset files
            #   - JSON files under bin/x64/plugins/cyber_engine_tweaks/mods
            #   - ModSettings user.ini, it contains all settings configurable via ModSettings -> https://www.nexusmods.com/cyberpunk2077/mods/4885
            #   - Bought properties from mod NCestate -> https://www.nexusmods.com/cyberpunk2077/mods/12857
            #   - Bought cryptocurrencies from mod cryptoexchange -> https://www.nexusmods.com/cyberpunk2077/mods/27666?tab=description
            #   - Bought stocks from mod stocks -> https://www.nexusmods.com/cyberpunk2077/mods/6319
            if (i.suffix.lower() == '.preset') or \
               (i.suffix.lower() == '.log') or \
               ('bin/x64/plugins/cyber_engine_tweaks/mods' in f and i.suffix.lower() == '.json') or \
               ('bin/x64/plugins/cyber_engine_tweaks/mods/cryptoexchange/data/persistent' in f) or \
               ('bin/x64/plugins/cyber_engine_tweaks/mods/stocks/data/persistent' in f) or \
               ('bin/x64/plugins/cyber_engine_tweaks/mods/NCestate/session' in f) or \
               ('red4ext/plugins/mod_settings' in f and i.name == 'user.ini'):
                continue
            if not(f in files_in_backup):
                result_files['delete'].append(i._raw_path)
            else:
                result_files['keep'].append(i._raw_path)

        # If nothing to delete
        if len(result_files['delete']) == 0:
            self.utils.printf("[*] There is nothing to delete")
            return

        # Print results and save to log
        self.utils.printf('[!] {0} mod files will be deleted', len(result_files['delete']))
        self.utils.printf('[!] {0} game files will be kept', len(result_files['keep']))
        with open (result_files_log, 'w') as f:
            f.write('FILES TO DELETE:\n  - ')
            f.write('\n  - '.join(result_files['delete']))
            f.write('\n\n\nFILES TO KEEP:\n  - ')
            f.write('\n  - '.join(result_files['keep']))

        # Ask to delete
        self.utils.printf('[!] Please read the log file {0} to check if files are correct', result_files_log); input('Press enter to continue...')
        if input('Do you want to delete the files? (answer with a "yes") -> ') != 'yes': return

        # Delete files
        for f in result_files['delete']:
            self.utils.printf('[!] Deleting file -> {0}', f)
            if not self.simulation_mode: 
                os.remove(f)

        # Delete database
        if not self.simulation_mode:
            self.database.backup() # backup before delete
            os.remove(self.database.path)

        self.utils.printf('[i] Please verify game files in steam')

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Script start
try:
    # Exit if not in linux
    if not sys.platform == "linux":
        print(bcolors.FAIL + str.format("Script only runs in linux, platform '{0}' detected.", sys.platform))
        sys.exit()

    # Globals/Constants
    script_version = "1.2"
    supported_formats = ['.zip', '.rar', '.7z']
    script_storage_path = os.path.join(os.environ['HOME'], '.cp2077')
    script_database_path = os.path.join(script_storage_path, 'database.json')
    script_database_backups_path = os.path.join(script_storage_path, 'database_backups/')
    script_settings_path = os.path.join(script_storage_path, 'settings.json')
    script_settings = {
        'CP2077': {
            'Path': ''
        },
        'NexusMods': {
            'ApiKey': ''
        }}
    usage_example=str.format('\
    \nUsage examples:\n\
        Install a mod               ->  {0} -i /home/user/Downloads/Mod.zip\n\
        Uninstall a mod             ->  {0} -u /home/user/Downloads/Mod.zip\n\
        Delete all installed mods   ->  {0} -r /home/user/Games/CyberpunkBackup.7z\n\
    ', os.path.basename(sys.argv[0]))

    # Args -> https://docs.python.org/3/library/argparse.html
    parser = argparse.ArgumentParser(formatter_class=argparse.MetavarTypeHelpFormatter, 
                                     description=str.format('Script to manage Cyberpunk 2077 mods in Linux. Version {0}', script_version),
                                     epilog="Supported archive file formats: "+', '.join(supported_formats))    
    parser.add_argument('--usage-examples', help='Display usage examples', action='store_true')
    parser.add_argument('--verbose', help='Display verbose messages', action='store_true')
    parser.add_argument('--simulation-mode', help='Enable simulation mode. No changes will be made in either CP\'s nor the script\'s database', action='store_true')
    parser.add_argument('--list-installed-mods', help='List all installed mods', action='store_true')
    parser.add_argument('--check-database', help='Load database and show metadata. No actions are made.', action='store_true')
    parser.add_argument('--check-mod-updates', help='Check for mod file updates', action='store_true')
    parser.add_argument('--version', action='store_true', help='show script\'s version')
    parser.add_argument('-i', '--install', help='Install mod.', type=str)
    parser.add_argument('-u', '--uninstall', help='uninstall mod.', type=str)
    parser.add_argument('-d', '--delete-archive', help='delete mod\'s archive when uninstalling.', action='store_true')
    parser.add_argument('-r', '--reset', help='Full reset. Will delete all mods. Confirmation will be asked.', type=str)
    args = parser.parse_args()

    # If usage asked
    if args.usage_examples:
        print(usage_example)
        sys.exit()

    # If version asked
    if args.version:
        Utils.printf('Version: {0}', script_version)
        sys.exit()

    # Create paths
    if not os.path.exists(script_storage_path): os.makedirs(script_storage_path)
    if not os.path.exists(script_database_backups_path): os.makedirs(script_database_backups_path)

    # Load/create settings
    if os.path.exists(script_settings_path):
        with open(script_settings_path, 'r') as f:
            script_settings = json.load(f)
    else:
        Utils().json_save_file(script_settings_path, script_settings)

    # Check for required args
    if not args.install and not args.uninstall and not args.reset and not args.check_database and not args.check_mod_updates and not args.list_installed_mods:
        parser.print_help()
        sys.exit()

    # If sim mode
    if args.simulation_mode:
        print("*******************")
        print("* SIMULATION MODE *")
        print("*******************")

    # Init classes
    utils = Utils(args.verbose)
    if args.verbose: utils.printf('Script version: {0}', script_version)
    mm = ModManager(utils, script_database_path, script_database_backups_path, script_settings['CP2077']['Path'], script_settings['NexusMods']['ApiKey'], args.simulation_mode)

    # Check CP2077 path
    if not (script_settings['CP2077']['Path'] and utils.isCP2077(script_settings['CP2077']['Path'])):
        raise Exception(str.format('CP2077.Path is not valid or not set in file {0}', script_settings_path))
        sys.exit()

    # Do actions
    # Check database
    if args.check_database:
        mm.database.show_info()
    # List installed mods
    elif args.list_installed_mods:
        mm.database.list_installed_mods()
    # Check updates
    elif args.check_mod_updates:
        mm.check_mod_updates()
    # Install
    elif args.install:
        mm.install(args.install)
        mm.database.load()
    # Uninstall
    elif args.uninstall:
        mm.uninstall(args.uninstall, args.delete_archive)
        mm.database.load()
    # Reset
    elif args.reset:
        print('***********')
        print('! WARNING !')
        print('***********')
        print('This action will delete every file not present in the given backup (-b flag).')
        print('This means that every non-vanilla file will be lost forever. Including mod generated files and some configs.')
        print('Mod settings "user.ini" will be skipped as well as jsons under "bin/x64/plugins/cyber_engine_tweaks/mods"')
        input('Press enter to continue or ctrl+c to exit...')
        mm.reset(args.reset)
    # Unsupported
    else:
        raise Exception(str.format('Action "{0}" not supported', args.action))

    # End
    print("[*] Done")

except KeyboardInterrupt:
        print('\nKeyboardInterrupt detected, exiting...')
        sys.exit()
except Exception as e:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    exc_lines = str(exc_tb.tb_lineno)
    cont = exc_tb.tb_next
    failsafe = 0
    while cont:
        exc_lines += ' -> ' + str(cont.tb_lineno)
        cont = cont.tb_next
        failsafe += 1
        if failsafe > 10: break
    print(str.format('Error:\n  - Name: {0}\n  - Type: {1}\n  - Line/s: {2}\n  - Description: {3}', fname, exc_type, exc_lines, e))