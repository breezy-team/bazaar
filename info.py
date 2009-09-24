bzr_plugin_name = "git"

dulwich_minimum_version = (0, 3, 3)

# versions ending in 'exp' mean experimental mappings
# versions ending in 'dev' mean development version
# versions ending in 'final' mean release (well tested, etc)
bzr_plugin_version = (0, 4, 2, 'dev', 0)

bzr_commands = ["svn-import", "svn-layout"]

bzr_compatible_versions = [(1, x, 0) for x in [15, 16, 17, 18]] + \
                          [(2, x, 0) for x in [0]]

bzr_minimum_version = bzr_compatible_versions[0]

bzr_maximum_version = bzr_compatible_versions[-1]

bzr_control_formats = {"Git":{'.git/': None}}
