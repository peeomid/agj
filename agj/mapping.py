from __future__ import annotations

from agj.models import InstanceInfo, ProcessInfo, SessionInfo


def map_instances(processes: list[ProcessInfo], sessions: list[SessionInfo]) -> list[InstanceInfo]:
    sessions_by_pid = {session.pid: session for session in sessions if session.pid is not None}
    instances: list[InstanceInfo] = []
    for proc in processes:
        matched = None
        for pid in proc.ancestry:
            matched = sessions_by_pid.get(pid)
            if matched is not None:
                break
        instances.append(InstanceInfo(process=proc, session=matched))
    return instances
