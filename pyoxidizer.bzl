# EXPERIMENTAL

def make_dist():
    return default_python_distribution(python_version="3.9")

def make_exe(dist):

    # A policy describes how the application resources are included in the
    # final artifact.
    policy = dist.make_python_packaging_policy()

    # Try to add resources to in-memory first. If that fails, add them to a
    # "lib" directory relative to the built executable. Needed by some Python
    # extension modules.
    #
    # This is not going to work, e.g. Django is not using importlib.resources
    # (https://code.djangoproject.com/ticket/30950). There's probably more.
    #
    #     policy.resources_location = "in-memory"
    #     policy.resources_location_fallback = "filesystem-relative:lib"
    #
    # This is safe:
    policy.resources_location = "filesystem-relative:lib"

    # Module that we want the embedded Python interpreter to execute for us.
    python_config = dist.make_python_interpreter_config()
    python_config.run_module = "a3m.cli.server"

    exe = dist.to_python_executable(
        name="a3m",
        packaging_policy=policy,
        config=python_config,
    )

    # Include dependencies and the a3m application sources.
    exe.add_python_resources(exe.pip_install(["-r", "requirements.txt"]))
    exe.add_python_resources(exe.read_package_root(
        path="./",
        packages=["a3m"],
    ))

    return exe

def make_embedded_resources(exe):
    return exe.to_embedded_resources()

def make_install(exe):
    files = FileManifest()
    files.add_python_resource(".", exe)

    return files

register_target("dist", make_dist)
register_target("exe", make_exe, depends=["dist"])
register_target("resources", make_embedded_resources, depends=["exe"], default_build_script=True)
register_target("install", make_install, depends=["exe"], default=True)

resolve_targets()
