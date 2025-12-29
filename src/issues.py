# src/issues.py

from __future__ import annotations

from typing import List, Optional

from .validate import Issue


def tag_issues(issues: List[Issue], ref_id: str) -> List[Issue]:
    """
    Return a new list of Issues with ref_id populated when missing.
    (Issue is frozen/immutable, so we construct new Issue objects.)
    """
    tagged: List[Issue] = []
    for i in issues:
        if i.ref_id is None:
            tagged.append(
                Issue(
                    severity=i.severity,
                    category=i.category,
                    message=i.message,
                    suggested_question=i.suggested_question,
                    ref_id=ref_id,
                )
            )
        else:
            tagged.append(i)
    return tagged


def tag_issue(issue: Issue, ref_id: str) -> Issue:
    """Tag a single Issue if it doesn't already have a ref_id."""
    if issue.ref_id is not None:
        return issue
    return Issue(
        severity=issue.severity,
        category=issue.category,
        message=issue.message,
        suggested_question=issue.suggested_question,
        ref_id=ref_id,
    )
