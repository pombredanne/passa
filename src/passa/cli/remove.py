# -*- coding=utf-8 -*-

from __future__ import absolute_import, unicode_literals

from ._base import BaseCommand


NAME = "remove"
DESC = "Remove given packages from project."


def main(options):
    from passa.lockers import PinReuseLocker
    from passa.projects import Project
    from .lock import lock

    default = (options.only != "dev")
    develop = (options.only != "default")

    project = Project(options.project_root)
    project.remove_keys_from_pipfile(
        options.packages, default=default, develop=develop,
    )

    locker = PinReuseLocker(project)
    success = lock(locker)
    if not success:
        return 1

    project._p.write()
    project._l.write()
    print("Written to project at", project.root)


class Command(BaseCommand):

    parsed_main = main

    def add_arguments(self):
        super(Command, self).add_arguments()
        self.parser.add_argument(
            "packages", metavar="package",
            nargs="+",
            help="package to remove (can be used multiple times)",
        )
        dev_group = self.parser.add_mutually_exclusive_group()
        dev_group.add_argument(
            "--dev", dest="only",
            action="store_const", const="dev",
            help="only try to remove from [dev-packages]",
        )
        dev_group.add_argument(
            "--default", dest="only",
            action="store_const", const="default",
            help="only try to remove from [packages]",
        )


if __name__ == "__main__":
    Command.run_current_module()
