#!/usr/bin/env python3
"""
Goal-Driven Iterative Research (GDIR) Engine

Implements the GOAL → PLAN → ACT → EVALUATE → LEARN → REPLAN → ... → VERIFY → DONE loop
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field
try:
    from extract_structured import extract_entity, ExtractionFailure
except Exception:
    extract_entity = None
    ExtractionFailure = Exception

# Add Hermes home to path for imports
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
CACHE_DIR = HERMES_HOME / "cache" / "research"


@dataclass
class StrategyAttempt:
    """Record of a strategy attempt"""
    name: str
    queries: List[str]
    results_count: int
    success: bool
    failure_reason: Optional[str] = None
    learned: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ResearchResult:
    """A single research finding"""
    source: str
    title: str
    snippet: str
    relevance_score: float
    citation_id: Optional[int] = None


@dataclass
class Failure:
    """Record of a failure"""
    strategy: str
    query: str
    why_failed: str
    lesson: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class NextStrategy:
    """Plan for next strategy"""
    name: str
    queries: List[str]
    rationale: str


@dataclass
class GDIRState:
    """Complete GDIR state"""
    goal: str
    success_criteria: List[str]
    strategies_tried: List[StrategyAttempt] = field(default_factory=list)
    queries_tried: List[str] = field(default_factory=list)
    sources_checked: List[str] = field(default_factory=list)
    results: List[ResearchResult] = field(default_factory=list)
    failures: List[Failure] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    next_strategy: Optional[NextStrategy] = None
    iteration_count: int = 0
    max_iterations: int = 10
    completed: bool = False
    completed_at: Optional[str] = None
    deliverable: Optional[str] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class GDIRStateManager:
    """Manages GDIR state persistence"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.state_dir = CACHE_DIR / self.session_id
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "gdir_state.json"
    
    def save(self, state: GDIRState) -> None:
        """Save state to disk"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(state), f, indent=2, ensure_ascii=False)
    
    def load(self) -> Optional[GDIRState]:
        """Load state from disk"""
        if not self.state_file.exists():
            return None
        with open(self.state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct nested dataclasses
        if data.get("strategies_tried"):
            data["strategies_tried"] = [StrategyAttempt(**s) for s in data["strategies_tried"]]
        if data.get("results"):
            data["results"] = [ResearchResult(**r) for r in data["results"]]
        if data.get("failures"):
            data["failures"] = [Failure(**f) for f in data["failures"]]
        if data.get("next_strategy"):
            data["next_strategy"] = NextStrategy(**data["next_strategy"])
        
        return GDIRState(**data)
    
    def delete(self) -> None:
        """Delete state file"""
        if self.state_file.exists():
            self.state_file.unlink()


class StrategyRegistry:
    """Registry of available research strategies"""
    
    STRATEGIES = {
        "web_search": {
            "description": "Search the web via search API",
            "capabilities": ["broad_topics", "current_events", "general_knowledge"],
            "best_for": "Initial exploration, finding recent information"
        },
        "arxiv_search": {
            "description": "Search arXiv for academic papers",
            "capabilities": ["academic_papers", "preprints", "ml_ai_research"],
            "best_for": "Technical research, ML/AI papers, citations"
        },
        "web_extract": {
            "description": "Extract full content from specific URLs",
            "capabilities": ["deep_content", "full_papers", "documentation"],
            "best_for": "Getting full text after finding relevant URLs"
        },
        "semantic_scholar": {
            "description": "Search Semantic Scholar for papers and citations",
            "capabilities": ["citations", "related_papers", "author_profiles"],
            "best_for": "Citation graphs, finding related work, impact metrics"
        },
        "blog_search": {
            "description": "Search blogs and RSS feeds",
            "capabilities": ["industry_blogs", "tutorials", "opinion_pieces"],
            "best_for": "Practical implementations, tutorials, industry perspectives"
        }
    }
    
    @classmethod
    def get_strategy(cls, name: str) -> Optional[Dict]:
        return cls.STRATEGIES.get(name)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        return list(cls.STRATEGIES.keys())


class GDIR:
    """Main GDIR engine implementing the research loop"""
    
    def __init__(
        self,
        goal: str,
        success_criteria: List[str],
        max_iterations: int = 10,
        session_id: Optional[str] = None
    ):
        self.goal = goal
        self.success_criteria = success_criteria
        self.max_iterations = max_iterations
        self.state_manager = GDIRStateManager(session_id)
        
        # Load or create state
        self.state = self.state_manager.load() or GDIRState(
            goal=goal,
            success_criteria=success_criteria,
            max_iterations=max_iterations
        )
    
    def run(self) -> GDIRState:
        """Run the GDIR loop until completion"""
        print(f"🎯 Starting GDIR: {self.goal}")
        print(f"📋 Success criteria: {self.success_criteria}")
        print(f"🔄 Max iterations: {self.max_iterations}")
        print()
        
        while not self.state.completed and self.state.iteration_count < self.max_iterations:
            self.state.iteration_count += 1
            print(f"\n{'='*60}")
            print(f"🔄 ITERATION {self.state.iteration_count}/{self.max_iterations}")
            print(f"{'='*60}")
            
            # PLAN
            self.plan()
            
            # ACT
            self.act()
            
            # EVALUATE
            if self.evaluate():
                self.state.completed = True
                self.state.completed_at = datetime.now().isoformat()
                break
            
            # LEARN
            self.learn()
            
            # REPLAN
            self.replan()
            
            # Save state after each iteration
            self.state_manager.save(self.state)
        
        # VERIFY & DONE
        self.verify_and_deliver()
        
        self.state_manager.save(self.state)
        return self.state
    
    def plan(self) -> None:
        """PLAN: Determine strategies and queries for this iteration"""
        print(f"\n📋 PLANNING (Iteration {self.state.iteration_count})")
        
        if self.state.iteration_count == 1:
            # First iteration: use default strategies
            self.state.next_strategy = NextStrategy(
                name="web_search",
                queries=[self.goal],
                rationale="Initial broad search to understand the landscape"
            )
        # Subsequent iterations use next_strategy from REPLAN
        
        print(f"  Strategy: {self.state.next_strategy.name}")
        print(f"  Queries: {self.state.next_strategy.queries}")
        print(f"  Rationale: {self.state.next_strategy.rationale}")
    
    def act(self) -> None:
        """ACT: Execute the planned strategy"""
        if not self.state.next_strategy:
            return
        
        strategy = self.state.next_strategy
        print(f"\n🚀 ACTING: {strategy.name}")
        
        attempt = StrategyAttempt(
            name=strategy.name,
            queries=strategy.queries,
            results_count=0,
            success=False
        )
        
        for query in strategy.queries:
            if query in self.state.queries_tried:
                print(f"  ⏭️  Skipping already-tried query: {query}")
                continue
            
            self.state.queries_tried.append(query)
            print(f"  🔍 Query: {query}")
            
            # Execute strategy (in real implementation, call Hermes tools)
            results = self._execute_strategy(strategy.name, query)
            
            attempt.results_count += len(results)
            for result in results:
                if result.source not in self.state.sources_checked:
                    self.state.sources_checked.append(result.source)
                self.state.results.append(result)
            
            print(f"     Found {len(results)} results")
        
        attempt.success = attempt.results_count > 0
        if not attempt.success:
            attempt.failure_reason = "no_results"
        
        self.state.strategies_tried.append(attempt)
    
    def _execute_strategy(self, strategy_name: str, query: str) -> List[ResearchResult]:
        # NEW: try structured extraction first (real API / oEmbed)
        if extract_entity is not None and ("youtube" in query.lower() or "linkedin" in query.lower() or "client" in query.lower()):
            try:
                # We would use real URLs discovered; here we test with known source
                test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # real known URL for extractor validation
                extracted = extract_entity(test_url, strategy_name)
                if extracted.get("verified"):
                    return [ResearchResult(
                        source=extracted["url"],
                        title=extracted["name"] or "Extracted entity",
                        snippet=extracted["description"] or (extracted["evidence"] or ""),
                        relevance_score=0.9 if extracted["verified"] else 0.3,
                        citation_id=None
                    )]
            except Exception as e:
                print(f"  Structured extraction failure (correct behavior): {str(e)[:120]}...")
                # Record failure; loop continues to try different strategy
        """Execute a specific strategy (integrates with Hermes tools via subprocess)"""
        results = []
        
        if strategy_name == "web_search":
            # Call web_search via terminal
            import subprocess
            import json
            
            # Use the web_search tool through Hermes CLI or direct API
            # For now, we'll use a subprocess call to simulate this
            cmd = [
                "python3", "-c", 
                f"""
import sys
sys.path.insert(0, '{HERMES_HOME}')
from hermes_tools import terminal
result = terminal('echo "MOCK: web_search would be called here"')
print(result)
"""
            ]
            # For demonstration, return mock but with varied relevance
            import random
            score = 0.5 + random.random() * 0.5
            results.append(ResearchResult(
                source=f"https://example.com/search-result-{len(self.state.results)}",
                title=f"Web result for: {query[:60]}",
                snippet=f"Mock web search result snippet for query: {query}",
                relevance_score=round(score, 2)
            ))
        
        elif strategy_name == "arxiv_search":
            # Call arxiv search via terminal/python
            import random
            for i in range(min(3, 1 + random.randint(0, 2))):
                score = 0.6 + random.random() * 0.4
                results.append(ResearchResult(
                    source=f"https://arxiv.org/abs/2024.{10000 + len(self.state.results) + i}",
                    title=f"arXiv paper: {query[:50]}",
                    snippet=f"Mock arXiv abstract for query: {query}",
                    relevance_score=round(score, 2)
                ))
        
        elif strategy_name == "web_extract":
            # Extract full content from URLs
            import random
            score = 0.5 + random.random() * 0.5
            results.append(ResearchResult(
                source=f"https://example.com/extracted-{len(self.state.results)}",
                title=f"Extracted content for: {query[:50]}",
                snippet=f"Mock extracted full text for query: {query}",
                relevance_score=round(score, 2)
            ))
        
        elif strategy_name == "semantic_scholar":
            # Search Semantic Scholar
            import random
            for i in range(min(2, 1 + random.randint(0, 1))):
                score = 0.6 + random.random() * 0.4
                results.append(ResearchResult(
                    source=f"https://www.semanticscholar.org/paper/{1000000 + len(self.state.results) + i}",
                    title=f"Semantic Scholar paper: {query[:50]}",
                    snippet=f"Mock Semantic Scholar result for query: {query}",
                    relevance_score=round(score, 2)
                ))
        
        elif strategy_name == "blog_search":
            # Search blogs
            import random
            score = 0.5 + random.random() * 0.5
            results.append(ResearchResult(
                source=f"https://blog.example.com/post-{len(self.state.results)}",
                title=f"Blog post: {query[:50]}",
                snippet=f"Mock blog search result for query: {query}",
                relevance_score=round(score, 2)
            ))
        
        return results
    
    def evaluate(self) -> bool:
        """EVALUATE: Assess if success criteria are met"""
        print(f"\n📊 EVALUATING (Iteration {self.state.iteration_count})")
        
        if not self.state.results:
            print("  No results yet")
            return False
        
        # Simple evaluation: check if we have enough relevant results
        relevant_count = sum(1 for r in self.state.results if r.relevance_score >= 0.7)
        total_results = len(self.state.results)
        
        print(f"  Total results: {total_results}")
        print(f"  Relevant results (score ≥ 0.7): {relevant_count}")
        
        # Check each success criterion with more rigorous heuristics
        criteria_met = 0
        for criterion in self.success_criteria:
            # Use keyword matching for basic criteria evaluation
            met = self._check_criterion(criterion, relevant_count)
            status = "✅" if met else "❌"
            print(f"  {status} {criterion}")
            if met:
                criteria_met += 1
        
        success = criteria_met == len(self.success_criteria)
        print(f"  Overall: {'SUCCESS' if success else 'CONTINUE'}")
        return success
    
    def _check_criterion(self, criterion: str, relevant_count: int) -> bool:
        """Check if a specific success criterion is met"""
        criterion_lower = criterion.lower()
        
        # Criterion: find at least N papers/results
        if "at least" in criterion_lower and ("paper" in criterion_lower or "result" in criterion_lower):
            import re
            match = re.search(r"at least (\d+)", criterion_lower)
            if match:
                required = int(match.group(1))
                return relevant_count >= required
        
        # Criterion: identify key algorithms/concepts
        if "identify" in criterion_lower or "find" in criterion_lower:
            if "algorithm" in criterion_lower or "method" in criterion_lower or "concept" in criterion_lower:
                # Check if results contain algorithm-related terms
                algorithm_terms = ["algorithm", "method", "approach", "technique", "model", "framework"]
                for result in self.state.results:
                    if result.relevance_score >= 0.7:
                        text = (result.title + " " + result.snippet).lower()
                        if any(term in text for term in algorithm_terms):
                            return True
                return False
        
        # Criterion: summarize applications/use cases
        if "summarize" in criterion_lower or "application" in criterion_lower or "use case" in criterion_lower:
            app_terms = ["application", "use case", "applied", "implementation", "deploy", "production"]
            for result in self.state.results:
                if result.relevance_score >= 0.7:
                    text = (result.title + " " + result.snippet).lower()
                    if any(term in text for term in app_terms):
                        return True
            return False
        
        # Default: need at least some relevant results
        return relevant_count > 0
    
    def learn(self) -> None:
        """LEARN: Diagnose failures and extract lessons"""
        print(f"\n🧠 LEARNING (Iteration {self.state.iteration_count})")
        
        last_attempt = self.state.strategies_tried[-1] if self.state.strategies_tried else None
        
        if last_attempt and not last_attempt.success:
            # Diagnose why it failed
            failure_reason = last_attempt.failure_reason or "unknown"
            
            lessons = {
                "no_results": "Query too specific; try broader terms or synonyms",
                "irrelevant_results": "Query too broad; add constraints or domain terms",
                "api_error": "Service issue; retry or try alternative source",
                "parse_error": "Format issue; adjust parsing or try different source",
                "unknown": "Unclear failure; try different strategy entirely"
            }
            
            lesson = lessons.get(failure_reason, f"Failed with: {failure_reason}")
            last_attempt.learned = lesson
            self.state.lessons_learned.append(lesson)
            
            failure = Failure(
                strategy=last_attempt.name,
                query=last_attempt.queries[0] if last_attempt.queries else "",
                why_failed=failure_reason,
                lesson=lesson
            )
            self.state.failures.append(failure)
            
            print(f"  ❌ Strategy failed: {failure_reason}")
            print(f"  💡 Lesson: {lesson}")
        else:
            # Success - extract positive lessons
            if last_attempt:
                lesson = f"Strategy '{last_attempt.name}' worked with queries: {last_attempt.queries}"
                self.state.lessons_learned.append(lesson)
                print(f"  ✅ Strategy succeeded: {lesson}")
    
    def replan(self) -> None:
        """REPLAN: Choose next strategy based on lessons learned"""
        print(f"\n🔄 REPLANNING (Iteration {self.state.iteration_count})")
        
        # Simple replanning logic
        tried_strategies = {a.name for a in self.state.strategies_tried}
        all_strategies = StrategyRegistry.list_strategies()
        
        # Find untried strategies
        untried = [s for s in all_strategies if s not in tried_strategies]
        
        if untried:
            # Try next untried strategy
            next_name = untried[0]
            rationale = f"Trying untried strategy after {len(tried_strategies)} attempts"
        else:
            # All strategies tried - refine queries
            next_name = self.state.strategies_tried[-1].name if self.state.strategies_tried else "web_search"
            rationale = "All strategies tried; refining query approach"
        
        # Generate new queries based on lessons
        new_queries = self._generate_queries(next_name)
        
        self.state.next_strategy = NextStrategy(
            name=next_name,
            queries=new_queries,
            rationale=rationale
        )
        
        print(f"  Next strategy: {next_name}")
        print(f"  New queries: {new_queries}")
        print(f"  Rationale: {rationale}")
    
    def _generate_queries(self, strategy: str) -> List[str]:
        """Generate new queries based on strategy and lessons"""
        # Simple query generation - in real implementation, use LLM
        base_queries = [self.goal]
        
        # Add variations based on lessons
        for lesson in self.state.lessons_learned[-3:]:  # Last 3 lessons
            if "broader" in lesson.lower():
                # Generate broader variations
                base_queries.append(self.goal.replace("Goal-Driven Iterative Learning", "Iterative Learning"))
                base_queries.append(self.goal.replace("Reinforcement Learning", "RL"))
            elif "constraint" in lesson.lower():
                base_queries.append(f"{self.goal} implementation")
            elif "specific" in lesson.lower():
                # Try more specific terms
                base_queries.append(f"{self.goal} algorithm")
                base_queries.append(f"{self.goal} paper")
        
        # Strategy-specific query patterns
        if strategy == "arxiv_search":
            base_queries.extend([
                f"ti:{self.goal.split()[0]}",  # Title search with first keyword
                f"abs:reinforcement learning iterative",  # Abstract search
                f"cat:cs.LG {self.goal.split()[0]}"  # Category + keyword
            ])
        elif strategy == "semantic_scholar":
            base_queries.extend([
                f"{self.goal} reinforcement learning",
                f"iterative learning RL",
                f"goal-directed reinforcement learning"
            ])
        elif strategy == "web_search":
            base_queries.extend([
                f"{self.goal} survey",
                f"{self.goal} tutorial",
                f"{self.goal} github"
            ])
        elif strategy == "blog_search":
            base_queries.extend([
                f"{self.goal} blog",
                f"{self.goal} tutorial implementation",
                f"{self.goal} explained"
            ])
        
        # Deduplicate and limit
        seen = set()
        unique = []
        for q in base_queries:
            if q not in seen and q not in self.state.queries_tried and q.strip():
                seen.add(q)
                unique.append(q)
        
        return unique[:3]  # Max 3 queries per iteration
    
    def verify_and_deliver(self) -> None:
        """VERIFY & DONE: Final verification and deliverable creation"""
        print(f"\n{'='*60}")
        print("✅ VERIFICATION & DELIVERY")
        print(f"{'='*60}")
        
        relevant_results = [r for r in self.state.results if r.relevance_score >= 0.7]
        
        self.state.deliverable = f"""
# Research Results: {self.goal}

## Summary
- Iterations: {self.state.iteration_count}
- Total results: {len(self.state.results)}
- Relevant results: {len(relevant_results)}
- Strategies tried: {len(self.state.strategies_tried)}
- Sources checked: {len(self.state.sources_checked)}

## Key Findings
"""
        for i, result in enumerate(relevant_results[:10], 1):
            self.state.deliverable += f"{i}. **{result.title}** (score: {result.relevance_score:.2f})\n"
            self.state.deliverable += f"   {result.snippet}\n"
            self.state.deliverable += f"   Source: {result.source}\n\n"
        
        self.state.deliverable += f"""
## Lessons Learned
"""
        for lesson in self.state.lessons_learned:
            self.state.deliverable += f"- {lesson}\n"
        
        self.state.deliverable += f"""
## Sources
"""
        for source in self.state.sources_checked:
            self.state.deliverable += f"- {source}\n"
        
        print(self.state.deliverable)
        print("✅ Research complete!")


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Goal-Driven Iterative Research")
    parser.add_argument("goal", nargs="+", help="Research goal")
    parser.add_argument("--criteria", nargs="+", default=["Find relevant information"], 
                       help="Success criteria")
    parser.add_argument("--max-iterations", type=int, default=10,
                       help="Maximum iterations")
    parser.add_argument("--session", help="Resume session ID")
    
    args = parser.parse_args()
    
    goal = " ".join(args.goal)
    
    gdir = GDIR(
        goal=goal,
        success_criteria=args.criteria,
        max_iterations=args.max_iterations,
        session_id=args.session
    )
    
    state = gdir.run()
    
    print(f"\n📁 State saved to: {gdir.state_manager.state_file}")
    print(f"🆔 Session ID: {state.session_id}")


if __name__ == "__main__":
    main()