#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from .monomer import Monomer, Team, ACTION_EVENT
from .team import ControllableTeam
import re
from ..lang import lang
from typing import Any, Optional, Awaitable, Callable
from ..types import SkillInfo, ActionCommand
from abc import ABC, abstractmethod
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from markdown.util import code_escape


class ControllableMonomer(Monomer, ABC):

    def __init__(self, team: ControllableTeam) -> None:
        super().__init__(team)
        if not isinstance(self.team, ControllableTeam):
            raise ValueError("The team must be an instance of ControllableTeam.")
        self.user_id = self.team.get_user_id()

    @abstractmethod
    async def get_skill_info_list(self) -> list[SkillInfo]:
        return []

    async def get_stat_text(self) -> str:
        another_team = self.team.scheduler.get_another_team(self.team)
        markdown = await lang.text(
            "stat.stat_header",
            self.user_id,
            code_escape(await self.team.get_team_name(self.user_id)),
            code_escape(await another_team.get_team_name(self.user_id)),
        )
        markdown += "\n"
        stats = await self.team.get_monomer_stat_list(self.user_id), await another_team.get_monomer_stat_list(
            self.user_id
        )
        for pos_index in range(max(len(stats[0]), len(stats[1]))):
            markdown += await lang.text(
                "stat.pos_line",
                self.user_id,
                pos_index + 1,
                stats[0][pos_index] if pos_index < len(stats[0]) else "",
                stats[1][pos_index] if pos_index < len(stats[1]) else "",
            )
            markdown += "\n"
        return markdown

    async def get_action_text(self) -> str:
        skill_text_list = []
        index = 0
        for skill in await self.get_skill_info_list():
            index += 1
            if skill["charge"] and self.get_charge_percent() < 1:
                skill_text_list.append(
                    await lang.text(
                        "action_text.skill_line",
                        self.user_id,
                        "",
                        f'~~{skill["name"]}~~',
                        await lang.text(f"action_text.cost.charge", self.user_id, self.final_skill_power[1]),
                    )
                )
            elif not self.team.has_skill_point(skill["cost"]):
                skill_text_list.append(
                    await lang.text(
                        "action_text.skill_line",
                        self.user_id,
                        "",
                        f'~~{skill["name"]}~~',
                        await lang.text(f"action_text.cost.normal", self.user_id, skill["cost"]),
                    )
                )
            elif skill["cost"] < 0:
                skill_text_list.append(
                    await lang.text(
                        "action_text.skill_line",
                        self.user_id,
                        index,
                        skill["name"],
                        await lang.text(f"action_text.cost.add", self.user_id, -skill["cost"]),
                    )
                )
            elif skill["charge"]:
                skill_text_list.append(
                    await lang.text(
                        "action_text.skill_line",
                        self.user_id,
                        index,
                        f'**{skill["name"]}**',
                        await lang.text(f"action_text.cost.charge", self.user_id, self.final_skill_power[1]),
                    )
                )
            else:
                skill_text_list.append(
                    await lang.text(
                        "action_text.skill_line",
                        self.user_id,
                        index,
                        skill["name"],
                        await lang.text(f"action_text.cost.normal", self.user_id, self.final_skill_power[1]),
                    )
                )
        return await lang.text(
            "action_text.header",
            self.user_id,
            self.team.get_skill_point()[0],
            self.final_skill_power[0],
            self.final_skill_power[1],
            self.get_charge_percent(True),
            "\n".join(skill_text_list),
        )

    @abstractmethod
    async def execute_skill(self, index: int, target: Optional[Monomer]) -> None:
        pass

    async def on_action(self, teams: list[Team]) -> None:
        markdown = await self.get_stat_text()
        markdown += "\n"
        markdown += await self.get_action_text()
        markdown += "\n"
        markdown += await lang.text("command_help", self.user_id)
        # TODO 战斗倒计时
        image = await md_to_pic(markdown)
        message = UniMessage().image(raw=image)
        while message := await self.get_action_command(message):
            pass

    async def get_action_command(self, message: UniMessage) -> Optional[UniMessage]:
        skill_info_list = await self.get_skill_info_list()
        waiter = WaitUserInput(
            message,
            self.user_id,
            lambda text: text in ["l", "b", "s"]
            or ((c := text.split(" "))[0].isdigit() and self.is_skill_ready(int(c[0]), skill_info_list)),
            "s",
        )
        await waiter.wait()
        command = waiter.get(lambda text: text.split(" "))
        if command[0] == "l":
            return UniMessage().image(raw=await md_to_pic(await self.get_action_list()))
        elif command[0] == "b":
            pass
        elif command[0] == "s":
            pass
        else:
            if len(command) >= 1:
                target_type = skill_info_list[int(command[0]) - 1]["target_type"]
                if target_type == "enemy":
                    target = self.team.scheduler.get_another_team(self.team).get_monomers()[int(command[1]) - 1]
                elif target_type == "self":
                    target = self.team.get_monomers()[int(command[1]) - 1]
                else:
                    target = None
            else:
                target = None
            await self.execute_skill(int(command[0]), target)

    async def get_action_list(self) -> str:
        markdown = await lang.text("action_list.header", self.user_id)
        original_action_value = 100000 / self.speed
        index = 0
        monomers = sorted(
            self.team.scheduler.get_monomers(),
            key=lambda target: target.get_action_value() if target != self else original_action_value,
        )
        markdown += await lang.text(
            "action_list.line",
            self.user_id,
            0,
            code_escape(await self.team.get_team_name(self.user_id)),
            await self.get_name(self.user_id),
            0,
        )
        for monomer in monomers:
            index += 1
            markdown += await lang.text(
                "action_list.line" if monomer != self else "action_list.line_self",
                self.user_id,
                index,
                code_escape(await monomer.get_team().get_team_name(self.user_id)),
                await monomer.get_name(self.user_id),
                round(monomer.get_action_value() if monomer != self else original_action_value),
            )
        return markdown

    def is_skill_ready(self, index: int, skill_info_list: list[SkillInfo]) -> bool:
        if index < 1 or index > len(skill_info_list):
            return False
        skill_info = skill_info_list[index - 1]
        if skill_info["charge"] and self.get_charge_percent() < 1:
            return False
        if not self.team.has_skill_point(skill_info["cost"]):
            return False
        return True


def get_monomer_indexs(monomer: ControllableMonomer, monomers: list[ControllableMonomer]) -> list[int]:
    indexs = []
    for i, m in enumerate(monomers):
        if m == monomer:
            indexs.append(i)
    return indexs
