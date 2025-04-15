# Dayhoff Configuration (`dayhoff.cfg`)

This file describes the configuration options for the Dayhoff system.

## Location

By default, Dayhoff looks for its configuration file at `~/.config/dayhoff/dayhoff.cfg`.

You can specify a different location by setting the `DAYHOFF_CONFIG_PATH` environment variable.

If the configuration file does not exist when Dayhoff starts, it will be created with default values.

## Format

The configuration file uses the standard INI format. Sections are denoted by `[SectionName]`, and key-value pairs are listed under each section. Comments start with `#` or `;`.

