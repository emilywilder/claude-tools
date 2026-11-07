# Install settings shared by the root justfile and every tool's justfile.
# Each tool's justfile imports this file.
#
# The root `just install` passes these values to each tool as environment
# variables, so overriding them at the top level works either way:
#   just prefix=/opt/ct install        or        PREFIX=/opt/ct just install

prefix := env("PREFIX", home_directory() / ".local")
bindir := env("BINDIR", prefix / "bin")
mode   := env("INSTALL_MODE", "copy")  # copy | link

set windows-shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]
