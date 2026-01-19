#!/usr/bin/env python3
"""
Security Article Workflow
Fetches security-related articles from RSS feeds and generates LinkedIn posts
"""

import os
import json
import feedparser
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import time
from dataclasses import dataclass
from enum import Enum
import logging
import anthropic
from bs4 import BeautifulSoup
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RSSFeed:
    """RSS feed configuration"""
    def __init__(self, url: str, name: str, keywords: List[str] = None):
        self.url = url
        self.name = name
        self.keywords = keywords or []


# Curated list of security-focused RSS feeds
SECURITY_RSS_FEEDS = [
    # General Security News
    RSSFeed("https://feeds.feedburner.com/TheHackersNews", "The Hacker News", 
            ["cyber security", "vulnerability", "breach", "exploit"]),
    RSSFeed("https://krebsonsecurity.com/feed/", "Krebs on Security",
            ["cyber security", "breach", "fraud"]),
    RSSFeed("https://www.schneier.com/feed/", "Schneier on Security",
            ["security", "cryptography", "privacy"]),
    RSSFeed("https://threatpost.com/feed/", "ThreatPost",
            ["threat", "vulnerability", "malware"]),
    RSSFeed("https://www.darkreading.com/rss.xml", "Dark Reading",
            ["security", "threat", "vulnerability"]),
    
    # Web3/Crypto Security
    RSSFeed("https://rekt.news/rss.xml", "Rekt News",
            ["defi", "hack", "exploit", "smart contract"]),
    RSSFeed("https://www.certik.com/resources/blog/rss.xml", "CertiK Blog",
            ["smart contract", "audit", "blockchain security"]),
    RSSFeed("https://blog.chainalysis.com/feed/", "Chainalysis",
            ["crypto", "blockchain", "defi", "crime"]),
    
    # Financial/Fintech Security
    RSSFeed("https://www.finextra.com/rss/headlines.aspx", "Finextra",
            ["fintech", "banking", "security", "fraud"]),
    
    # OWASP and Web Security
    RSSFeed("https://owasp.org/feed.xml", "OWASP",
            ["owasp", "web security", "vulnerability"]),
    RSSFeed("https://portswigger.net/daily-swig/rss", "The Daily Swig",
            ["web security", "vulnerability", "exploit"]),
    
    # Security Research
    RSSFeed("https://googleprojectzero.blogspot.com/feeds/posts/default", "Google Project Zero",
            ["zero day", "vulnerability", "exploit"]),
    RSSFeed("https://www.bleepingcomputer.com/feed/", "BleepingComputer",
            ["malware", "ransomware", "security"]),
    
    # Additional Security Sources
    RSSFeed("https://www.securityweek.com/feed/", "SecurityWeek",
            ["security", "breach", "vulnerability"]),
    RSSFeed("https://feeds.arstechnica.com/arstechnica/security", "Ars Technica Security",
            ["security", "breach", "vulnerability"]),
]

# Topic keywords for filtering
TOPIC_KEYWORDS = {
    "cyber_security": ["cyber", "security", "breach", "attack", "vulnerability", "exploit"],
    "product_security": ["product security", "software security", "application security"],
    "defi_hacks": ["defi", "decentralized finance", "liquidity", "protocol hack", "rug pull"],
    "fintech_hacks": ["fintech", "banking", "financial", "payment", "fraud"],
    "economic_security": ["economic security", "financial security", "market manipulation"],
    "web3_hacks": ["web3", "blockchain", "crypto", "nft", "smart contract"],
    "smart_contract": ["smart contract", "audit", "solidity", "ethereum", "blockchain"],
    "web3_threats": ["web3 threat", "crypto threat", "blockchain attack", "51% attack"],
    "web2_threats": ["web2", "traditional security", "server", "database", "api"],
    "owasp": ["owasp", "top 10", "web application", "injection", "xss", "csrf"],
    "fintech_threats": ["fintech threat", "banking malware", "financial fraud", "payment security"],
    "defi_threats": ["defi threat", "flash loan", "price oracle", "mev", "sandwich attack"],
}


@dataclass
class Article:
    """Represents a fetched article"""
    title: str
    url: str
    description: str
    published_date: str
    source: str
    relevance_score: float = 0.0
    content_preview: str = ""


class RSSArticleFetcher:
    """Fetches articles from RSS feeds"""
    
    def __init__(self):
        self.feeds = SECURITY_RSS_FEEDS
        self.topic_keywords = TOPIC_KEYWORDS
        
    def fetch_articles(self, days_back: int = 3) -> List[Article]:
        """Fetch articles from RSS feeds for the last N days"""
        articles = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        for feed in self.feeds:
            logger.info(f"Fetching from {feed.name} ({feed.url})")
            feed_articles = self._fetch_feed_articles(feed, cutoff_date)
            articles.extend(feed_articles)
            time.sleep(0.5)  # Be polite to servers
        
        # Remove duplicates based on URL
        unique_articles = {}
        for article in articles:
            # Use URL hash as key to handle duplicates
            url_hash = hashlib.md5(article.url.encode()).hexdigest()
            if url_hash not in unique_articles:
                unique_articles[url_hash] = article
        
        return list(unique_articles.values())
    
    def _fetch_feed_articles(self, feed: RSSFeed, cutoff_date: datetime) -> List[Article]:
        """Fetch articles from a specific RSS feed"""
        try:
            parsed_feed = feedparser.parse(feed.url)
            
            if parsed_feed.bozo:
                logger.warning(f"Feed parsing issue for {feed.name}: {parsed_feed.bozo_exception}")
            
            articles = []
            for entry in parsed_feed.entries[:20]:  # Limit to 20 most recent per feed
                # Parse publication date
                pub_date = self._parse_date(entry)
                if not pub_date or pub_date < cutoff_date:
                    continue
                
                # Check if article matches our security topics
                if not self._is_relevant(entry, feed):
                    continue
                
                # Extract article data
                title = entry.get('title', 'No title')
                url = entry.get('link', '')
                
                # Try different fields for description
                description = (
                    entry.get('summary', '') or 
                    entry.get('description', '') or 
                    entry.get('content', [{}])[0].get('value', '')
                )
                
                # Clean HTML from description
                if description:
                    soup = BeautifulSoup(description, 'html.parser')
                    description = soup.get_text()[:500]
                
                article = Article(
                    title=title,
                    url=url,
                    description=description,
                    published_date=pub_date.isoformat(),
                    source=feed.name,
                    content_preview=description[:300] if description else ""
                )
                
                articles.append(article)
            
            logger.info(f"Found {len(articles)} relevant articles from {feed.name}")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching {feed.name}: {e}")
            return []
    
    def _parse_date(self, entry: Dict) -> Optional[datetime]:
        """Parse publication date from feed entry"""
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
        
        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    time_struct = getattr(entry, field)
                    return datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)
                except:
                    continue
        
        # Try parsing string dates
        date_strings = ['published', 'updated', 'created']
        for field in date_strings:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    return datetime.fromisoformat(getattr(entry, field).replace('Z', '+00:00'))
                except:
                    continue
        
        return None
    
    def _is_relevant(self, entry: Dict, feed: RSSFeed) -> bool:
        """Check if article is relevant to security topics"""
        # Combine title and description for checking
        text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
        
        # Check feed-specific keywords first
        if feed.keywords:
            for keyword in feed.keywords:
                if keyword.lower() in text:
                    return True
        
        # Check against all topic keywords
        for topic, keywords in self.topic_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return True
        
        return False


class ArticleAnalyzer:
    """Analyzes and ranks articles for relevance"""
    
    def __init__(self, claude_api_key: Optional[str] = None):
        self.api_key = claude_api_key or os.getenv("CLAUDE_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
    
    def analyze_and_select(self, articles: List[Article], max_articles: int = 3) -> List[Article]:
        """Analyze articles and select the most relevant ones"""
        if not articles:
            return []
        
        # Score articles based on various factors
        for article in articles:
            article.relevance_score = self._calculate_relevance(article)
        
        # Sort by relevance and recency
        sorted_articles = sorted(
            articles,
            key=lambda x: (x.relevance_score, x.published_date),
            reverse=True
        )
        
        # Use AI to further refine selection if available
        if self.api_key and len(sorted_articles) > max_articles:
            return self._ai_select_articles(sorted_articles[:10], max_articles)
        
        return sorted_articles[:max_articles]
    
    def _calculate_relevance(self, article: Article) -> float:
        """Calculate basic relevance score"""
        score = 0.0
        
        # Check for high-impact keywords
        high_impact_words = [
            "critical", "breach", "hack", "vulnerability", "exploit",
            "million", "billion", "attack", "compromised", "urgent"
        ]
        
        text = f"{article.title} {article.description}".lower()
        for word in high_impact_words:
            if word in text:
                score += 1.0
        
        # Boost for recent articles
        try:
            pub_date = datetime.fromisoformat(article.published_date.replace("Z", "+00:00"))
            days_old = (datetime.now(pub_date.tzinfo) - pub_date).days
            if days_old == 0:
                score += 2.0
            elif days_old == 1:
                score += 1.0
        except:
            pass
        
        return score
    
    def _ai_select_articles(self, articles: List[Article], max_articles: int) -> List[Article]:
        """Use AI to select the most relevant articles"""
        if not self.client:
            return articles[:max_articles]
        
        try:
            article_summaries = "\n\n".join([
                f"{i+1}. Title: {a.title}\nDescription: {a.description}\nSource: {a.source}"
                for i, a in enumerate(articles)
            ])
            
            prompt = f"""You are an MBA cyber security expert selecting the most important and relevant articles for a LinkedIn audience.
            
Select the {max_articles} most important articles from the following list. Consider:
- Impact on web3, fintech, defi, webapp businesses and professionals
- Novelty and timeliness of the information
- Actionable insights for business professionals
- Relevance to current startup security trends
- An audience of founders, startups, angel investors
- Less focus on highly technical cyber security articles like 0-day exploitation
- More focus on specific appsec and cyber security strategies that could have helped in the articles

Articles:
{article_summaries}

Return only the numbers of the selected articles as a comma-separated list (e.g., "1,3,5")."""
            
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=50,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            selected_indices = response.content[0].text.strip().split(",")
            selected_articles = []
            
            for idx_str in selected_indices:
                try:
                    idx = int(idx_str.strip()) - 1
                    if 0 <= idx < len(articles):
                        selected_articles.append(articles[idx])
                except:
                    continue
            
            return selected_articles[:max_articles] if selected_articles else articles[:max_articles]
            
        except Exception as e:
            logger.error(f"AI selection failed: {e}")
            return articles[:max_articles]


class LinkedInPostGenerator:
    """Generates LinkedIn posts from selected articles"""
    
    def __init__(self, claude_api_key: Optional[str] = None):
        self.api_key = claude_api_key or os.getenv("CLAUDE_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
    
    def generate_post(self, articles: List[Article]) -> str:
        """Generate a LinkedIn post from selected articles"""
        if not articles:
            return self._generate_fallback_post()
        
        if self.api_key:
            return self._generate_ai_post(articles)
        else:
            return self._generate_template_post(articles)
    
    def _generate_ai_post(self, articles: List[Article]) -> str:
        """Generate post using AI"""
        if not self.client:
            return self._generate_template_post(articles)
            
        try:
            article_context = "\n\n".join([
                f"Article {i+1}:\nTitle: {a.title}\nDescription: {a.description}\nURL: {a.url}"
                for i, a in enumerate(articles)
            ])
            
            prompt = f"""You are writing LinkedIn posts for a cyber security consulting company. 

- Direct, no fluff
- Mildly bro-y. A youthful tone that expresses excitement.
- Shares practical lessons for founders who are thinking about security
- Speaks founder-to-founder, not consultant-to-client
- Uses "I" not "we"
- Short paragraphs, easy to scan
- Ends with question or light CTA
            
            
            Create a compelling LinkedIn post (1-2 paragraphs) based on these security articles. Use all of the articles.
            
Requirements:
- Highlight key takeaways and insights
- Make it relevant for business leaders. Speak security to a business audience
- Include specific details or statistics if available
- Professional but engaging tone
- If appropriate and natural, include a call to action to visit https://buildsafe.app for a free 30-minute security consultation
- Do NOT use hashtags, emojie, em dashes, or other signifiers of generative AI
- Keep it concise and impactful

Articles:
{article_context}

Generate the LinkedIn post:"""
            
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=400,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            post = response.content[0].text.strip()
            
            # Add article links at the end
            post += "\n\nSources:\n"
            for i, article in enumerate(articles, 1):
                post += f"{i}. {article.title}: {article.url}\n"
            
            return post
            
        except Exception as e:
            logger.error(f"AI post generation failed: {e}")
            return self._generate_template_post(articles)
    
    def _generate_template_post(self, articles: List[Article]) -> str:
        """Generate post using template (fallback)"""
        if len(articles) == 1:
            post = f"""🔐 Security Alert: {articles[0].title}

{articles[0].description}

This development highlights the evolving landscape of security threats facing organizations today. Staying informed and proactive is crucial for protecting your digital assets.

Concerned about your security posture? Visit https://buildsafe.app to schedule a free 30-minute consultation with security experts.

📰 Read more: {articles[0].url}"""
        else:
            post = f"""🔐 This Week in Security: Critical Developments You Need to Know

Today's security landscape is rapidly evolving with several significant developments:

"""
            for i, article in enumerate(articles, 1):
                post += f"{i}. {article.title} - {article.description[:100]}...\n\n"
            
            post += """These incidents underscore the importance of robust security practices and continuous vigilance.

Need help assessing your security readiness? Visit https://buildsafe.app for a free 30-minute consultation.

📰 Sources:"""
            for article in articles:
                post += f"\n• {article.url}"
        
        return post
    
    def _generate_fallback_post(self) -> str:
        """Generate a generic post when no articles are available"""
        return """🔐 Stay Ahead of Security Threats

In today's rapidly evolving digital landscape, staying informed about the latest security threats and best practices is crucial for protecting your organization.

Whether you're dealing with web3 vulnerabilities, fintech security, or traditional cyber threats, having the right security strategy is essential.

Ready to strengthen your security posture? Visit https://buildsafe.app to schedule a free 30-minute consultation with our security experts."""


class SecurityWorkflow:
    """Main workflow orchestrator"""
    
    def __init__(self, claude_api_key: Optional[str] = None):
        self.fetcher = RSSArticleFetcher()
        self.analyzer = ArticleAnalyzer(claude_api_key)
        self.generator = LinkedInPostGenerator(claude_api_key)
    
    def run(self, days_back: int = 3, max_articles: int = 3) -> Dict:
        """Run the complete workflow"""
        logger.info(f"Starting security article workflow for last {days_back} days")
        
        # Fetch articles
        logger.info("Fetching articles...")
        all_articles = self.fetcher.fetch_articles(days_back)
        logger.info(f"Fetched {len(all_articles)} total articles")
        
        # Analyze and select top articles
        logger.info("Analyzing and selecting top articles...")
        selected_articles = self.analyzer.analyze_and_select(all_articles, max_articles)
        logger.info(f"Selected {len(selected_articles)} articles")
        
        # Generate LinkedIn post
        logger.info("Generating LinkedIn post...")
        linkedin_post = self.generator.generate_post(selected_articles)
        
        # Prepare results
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_articles_found": len(all_articles),
            "selected_articles": [
                {
                    "title": a.title,
                    "url": a.url,
                    "description": a.description,
                    "source": a.source,
                    "published": a.published_date,
                    "relevance_score": a.relevance_score
                }
                for a in selected_articles
            ],
            "linkedin_post": linkedin_post
        }
        
        # Save results
        output_file = f"security_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to {output_file}")
        
        # Print the post
        print("\n" + "="*60)
        print("GENERATED LINKEDIN POST:")
        print("="*60)
        print(linkedin_post)
        print("="*60 + "\n")
        
        return results


def main():
    """Main entry point"""
    # Load API keys from environment or config
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    
    if not claude_api_key:
        logger.warning("No Claude API key found. Using template-based generation. Set CLAUDE_API_KEY for AI-powered posts.")
    
    # Create and run workflow
    workflow = SecurityWorkflow(claude_api_key)
    results = workflow.run(days_back=3, max_articles=3)
    
    print(f"\nWorkflow completed successfully!")
    print(f"Total articles found: {results['total_articles_found']}")
    print(f"Articles selected: {len(results['selected_articles'])}")
    print(f"Output saved to: security_post_*.json")


if __name__ == "__main__":
    main()