import os
import subprocess
import re
from kaot.feature_manager.feature import register_feature
from kaot.feature_manager.feature.base import BaseFeature
from kaot.utils.log import get_logger

logger = get_logger(__name__)

FEATURE_NAME = "config_core_isolation"
FEATURE_DES = "配置核隔离"


@register_feature(scenarios=["boundary_gateway_appliance"])
class ConfigCoreIsolation(BaseFeature):
    name: str = FEATURE_NAME
    isolcpus: str = "1-5"
    nohz_full: str = "1-5"
    rcu_nocbs: str = "1-5"

    def get_current_config(self) -> dict:
        config_keys = [k for k in self.__dict__.keys() if k != "name"]
        self.deploy = "NA"
        self.isolcpus = "NA"
        self.nohz_full = "NA"
        self.rcu_nocbs = "NA"
        with open("/etc/default/grub", "r") as f:
            # Target fields are all in the GRUB_CMDLINE_LINUX line
            content = f.read()
            match = re.search(
                r'^\s*GRUB_CMDLINE_LINUX\s*=\s*"([^"]*)"', content, re.MULTILINE
            )
            if match:
                cmdline_value = match.group(1)
                for part in cmdline_value.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k in config_keys:
                            self.__dict__[k] = v
            else:
                raise RuntimeError("GRUB_CMDLINE_LINUX not found")
        config = self.model_dump()
        logger.debug(f"Feature {self.name} current config yaml is generated")
        return config

    def _validate_cpu_list(self, cpu_str: str):
        """
        Validate whether the CPU list string is valid
        """
        total_cpus = os.cpu_count() or 0
        for part in cpu_str.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    start, end = map(int, part.split("-"))
                except ValueError:
                    raise RuntimeError(f"Invalid range format: {part}")
                if start > end:
                    raise RuntimeError(
                        f"Invalid range: {part} (start greater than end)"
                    )
                if start < 0 or end >= total_cpus:
                    raise RuntimeError(
                        f"CPU ID out of bounds: {part}, total CPUs = {total_cpus}"
                    )
            else:
                try:
                    cpu = int(part)
                except ValueError:
                    raise RuntimeError(f"Invalid CPU ID: {part}")
                if cpu < 0 or cpu >= total_cpus:
                    raise RuntimeError(
                        f"CPU ID out of bounds: {cpu}, total CPUs = {total_cpus}"
                    )

    def _update_grub(
        self,
        isolcpus: str,
        nohz_full: str,
        rcu_nocbs: str,
        grub_file="/etc/default/grub",
    ):
        """
        Modify the GRUB_CMDLINE_LINUX line in /etc/default/grub
        """
        with open(grub_file, "r") as f:
            lines = f.readlines()

        new_lines = []
        pattern = re.compile(r'^(GRUB_CMDLINE_LINUX\s*=\s*")(.*)(")$')

        for line in lines:
            match = pattern.match(line)
            if match:
                prefix, content, suffix = match.groups()

                # Remove existing core isolation parameters to avoid duplication
                content = re.sub(r"isolcpus=\S+", "", content)
                content = re.sub(r"nohz_full=\S+", "", content)
                content = re.sub(r"rcu_nocbs=\S+", "", content)

                # Append new parameters
                extra = (
                    f"isolcpus={isolcpus} nohz_full={nohz_full} rcu_nocbs={rcu_nocbs}"
                )
                # Clean up extra spaces before appending
                content = content.strip()
                if content:
                    content = f"{content} {extra}"
                else:
                    content = extra

                line = f"{prefix}{content}{suffix}\n"

            new_lines.append(line)

        # Write back to file
        with open(grub_file, "w") as f:
            f.writelines(new_lines)

        logger.warning(
            "GRUB_CMDLINE_LINUX has been updated. Changes will take effect after reboot."
        )

    def _apply_config_impl(self):
        """
        Apply core isolation configuration based on settings
        """
        isolcpus = self.isolcpus
        nohz_full = self.nohz_full
        rcu_nocbs = self.rcu_nocbs

        if not (isolcpus == nohz_full == rcu_nocbs):
            raise RuntimeError(
                f"Configuration mismatch: isolcpus={isolcpus}, nohz_full={nohz_full}, rcu_nocbs={rcu_nocbs}"
            )
        self._validate_cpu_list(isolcpus)
        self._update_grub(isolcpus=isolcpus, nohz_full=nohz_full, rcu_nocbs=rcu_nocbs)

        commands = [
            "grub2-mkconfig -o /boot/grub2/grub.cfg",
        ]

        timeout = 10
        for cmd in commands:
            logger.info(f"Executing: {cmd}")
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            if result.stdout.strip():
                logger.info(f"Command {cmd} output: {result.stdout.strip()}")