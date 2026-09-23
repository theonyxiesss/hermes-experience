#!/usr/bin/env python3
"""
Hermes Integration for GDIR

Provides a skill command that integrates GDIR with Hermes tools
"""

import json
import os
import sys
import subprocess
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
GDIR_SCRIPT = HERMES_HOME / "skills" / "research" / "goal-driven-research" / "scripts" / "gdir.py"


def run_gdir(goal: str, criteria: list = None, max_iterations: int = 10, session_id: str = None) -> dict:
    """Run GDIR via subprocess and return state"""
    
    cmd = [sys.executable, str(GDIR_SCRIPT), goal]
    
    if criteria:
        cmd.extend(["--criteria"] + criteria)
    
    if max_iterations:
        cmd.extend(["--max-iterations", str(max_iterations)])
    
    if session_id:
        cmd.extend(["--session", session_id])
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=HERMES_HOME)
    
    if result.returncode != 0:
        return {"error": result.stderr}
    
    # Parse output to extract session ID and state file
    output = result.stdout
    session_id = None
    state_file = None
    
    for line in output.split('\n'):
        if line.startswith("🆔 Session ID:"):
            session_id = line.split(":")[1].strip()
        elif line.startswith("📁 State saved to:"):
            state_file = line.split(":")[1].strip()
    
    return {
        "session_id": session_id,
        "state_file": state_file,
        "output": output
    }


def resume_gdir(session_id: str, goal: str = None) -> dict:
    """Resume a GDIR session"""
    if not goal:
        # Load goal from state file
        state_file = HERMES_HOME / "cache" / "research" / session_id / "gdir_state.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            goal = state.get("goal", "")
    
    return run_gdir(goal or "", session_id=session_id)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Hermes GDIR Integration")
    parser.add_argument("goal", nargs="+", help="Research goal")
    parser.add_argument("--criteria", nargs="+", default=["Find relevant information"])
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--session", help="Resume session ID")
    
    args = parser.parse_args()
    
    goal = " ".join(args.goal)
    result = run_gdir(goal, args.criteria, args.max_iterations, args.session)
    
    print(json.dumps(result, indent=2))