"""状态机定义 — EpisodeState + GapType 枚举。"""

from enum import Enum


class EpisodeState(Enum):
    PLANNING    = "episode_creating"              # Author 规划中
    RUNNING     = "episode_created"               # 内循环进行中
    SUMMARIZING = "episode_ended_pending_summary"  # 等待 Author 总结
    DONE        = "summarized"                     # 本幕完成，可推进

    def __str__(self) -> str:
        return self.value


class GapType(Enum):
    SMALL = "small_gap"    # 时间连续、地点相近、角色重叠 → 保留上下文
    BIG   = "big_gap"      # 时间跳转、章节推进 → Agent 自行决定清理
