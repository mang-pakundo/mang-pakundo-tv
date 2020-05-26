import sys
import xml.etree.ElementTree as ET
import semver

addon_tag = '<addon id="plugin.video.naisko" name="naIsko" version="%s" provider-name="mang.pakundo">'

def main(addon_xml, info_xml, bump):
    tree = ET.parse(addon_xml)
    root = tree.getroot()
    parsed_ver = root.attrib['version']
    version = semver.VersionInfo.parse(parsed_ver)
    print('Current version: %s' % version)

    new_version = version
    if bump == 'patch':
        new_version = version.bump_patch()
    elif bump == 'minor':
        new_version = version.bump_minor()
    elif bump == 'major':
        new_version = version.bump_major()
    print('Bumping %s to new version: %s' % (bump, new_version))

    with open(addon_xml) as f:
        new_addon_xml = f.read().replace(addon_tag % str(version), addon_tag % str(new_version))
    with open(addon_xml, 'w') as f:
        print('Writing %s' % addon_xml)
        f.write(new_addon_xml)

    with open(info_xml) as f:
        new_info_xml = f.read().replace(addon_tag % str(version), addon_tag % str(new_version))
    with open(info_xml, 'w') as f:
        print('Writing %s' % info_xml)
        f.write(new_info_xml)

if __name__ == '__main__':
    addon_xml = sys.argv[1]
    info_xml = sys.argv[2]
    bump = sys.argv[3]
    main(addon_xml, info_xml, bump)