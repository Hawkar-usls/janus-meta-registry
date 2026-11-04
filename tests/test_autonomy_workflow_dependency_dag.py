"""Prevent expensive GitHub Actions feedback loops in the JANUS autonomy witness DAG.

No network. Changing either independent witness to wake its own parent loop
would create a self-triggering chain of GitHub hosted worker jobs.
"""
from __future__ import annotations
import ast
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
WFDIR=ROOT/".github"/"workflows"
FILES=(
    "janus-autonomy-roadmap-loop.yml",
    "janus-rowan-ecosystem-sync-witness.yml",
    "janus-cross-organ-source-witness.yml",
)

def spec(path):
    doc=path.read_text(encoding="utf-8")
    m=re.search(r"(?m)^name:\s*(.+)$",doc)
    if m is None:
        raise AssertionError("Workflow missing immutable name")
    name=m.group(1).strip().strip("'\\"")
    m=re.search(r"(?m)^  workflow_run:\s*\n    workflows:\s*(\[[^\n]+\])",doc)
    if m is None:
        raise AssertionError("A reviewed witness workflow lost its explicit trigger allowlist")
    upstream=ast.literal_eval(m.group(1))
    if type(upstream) is not list or not all(type(x) is str for x in upstream):
        raise AssertionError("Unreviewed dynamic workflow trigger")
    return name,upstream,doc

class AutonomyWorkflowDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries=[spec(WFDIR/n) for n in FILES]
        cls.graph={name:set(upstream) for name,upstream,_ in cls.entries}

    def test_three_workflows_have_unique_immutable_names(self):
        self.assertEqual(len(self.graph),len(FILES))

    def test_independent_witnesses_respond_to_parent_without_back_edge(self):
        parent="JANUS Autonomous Roadmap and Continuation"
        witnesses={"JANUS Rowan Ecosystem Independent Sync Witness",
                   "JANUS Cross Organ Source-Bound Evidence Witness"}
        self.assertIn(parent,self.graph)
        for name in witnesses:
            self.assertIn(parent,self.graph[name])
            self.assertNotIn(name,self.graph[parent])

    def test_no_transitive_trigger_cycle_within_witness_graph(self):
        visited=set()
        visiting=set()
        def dfs(name):
            if name in visiting:
                raise AssertionError("Unbounded GitHub workflow_run recursion: "+name)
            if name in visited:
                return
            visiting.add(name)
            for upstream in self.graph.get(name,()):
                if upstream in self.graph:
                    dfs(upstream)
            visiting.remove(name)
            visited.add(name)
        for name in self.graph:
            dfs(name)
        self.assertEqual(visited,set(self.graph))

    def test_same_repo_success_only_and_no_pull_request_execution(self):
        parent=self.entries[0][2]
        for name,upstream,doc in self.entries:
            self.assertIn("github.event.workflow_run.conclusion == 'success'",doc)
            self.assertIn("github.event.workflow_run.head_branch == 'main'",doc)
            self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository",doc)
        self.assertIn("github.event_name != 'pull_request'",parent)
        self.assertIn("cron: '19 * * * *'",parent)
        self.assertIn("cancel-in-progress: false",parent)
        self.assertIn("AUTONOMY_WAKE_AUTHORITY_DELTA=0",parent)

    def test_no_paid_provider_or_full_authority_in_wake_definition(self):
        parent=self.entries[0][2]
        self.assertNotIn("ROWAN_API_KEY",parent)
        self.assertNotIn("OPENAI_API_KEY",parent)
        self.assertNotIn("git push --force",parent)
        self.assertIn("only loop metadata; preserve history",parent)
        self.assertIn("independently reread exact source commits",parent.lower())

if __name__=="__main__":
    unittest.main()
