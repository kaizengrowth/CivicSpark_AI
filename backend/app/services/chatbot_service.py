import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import Settings
from app.core.llm import get_chat_client
from app.models.campaign import Campaign
from app.models.document import Document
from app.models.meeting import AgendaItem, Meeting
from app.services.agenda_parser import normalize_item_number
from app.services.budget_service import format_budget_lines, lookup_budget_lines
from app.services.intent_router import classify_intent
from app.services.research_service import ResearchService
from app.services.vector_service import VectorService
from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ChatbotService:
    """Chatbot service backed by the configured LLM (Llama by default)
    with document-search and research capabilities"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

        self.client, self.model = get_chat_client(settings)
        if self.client is None:
            logger.warning(
                "No LLM configured (set LLM_API_KEY or OPENAI_API_KEY). "
                "Chatbot will use fallback responses only."
            )

        self.research_service = ResearchService(settings)
        self.vector_service = VectorService(settings, db)

    def get_system_prompt(self) -> str:
        """Get the enhanced system prompt for the chatbot"""
        return """You are CityCamp AI, a knowledgeable and friendly assistant focused on Tulsa, Oklahoma civic engagement and city government.

You have extensive knowledge about Tulsa government, civic processes, city services, local politics, and community engagement opportunities. Feel free to provide detailed, conversational responses that help people understand and get involved in their local government.

RESPONSE APPROACH:
- **Never invent specific figures, vote outcomes, or ordinance text.** For dollar amounts use the lookup_budget_line tool; for what Council did use document search and get_agenda_item; cite the source. If the corpus doesn't contain the answer, say so plainly and point to the official source (cityoftulsa.org, tulsacouncil.org) instead of guessing
- **Contested topics** (housing, policing, public safety, budgets, accountability): do not soft-pedal, evade, or take sides. Present what Council actually did (with citations) as distinct from what advocates or officials claim; surface staff reports and public comment records when they exist in the corpus; if the corpus only covers one side, say so. You serve residents' right to know, not the city's narrative
- Be conversational, helpful, and encouraging
- Provide as much detail as needed to fully answer questions
- Use your knowledge to give comprehensive, nuanced responses
- **Actively use web search** for questions about recent events, current policies, upcoming meetings, or when you need to verify current information
- Use **bold** for key terms when it helps readability
- For section headers, use smaller formatting like *Section Name:* instead of **LARGE HEADERS:**
- Include specific resources, contacts, and next steps when relevant
- When searching the web, prioritize official Tulsa government websites and authoritative local news sources

CAPABILITIES & KNOWLEDGE:
- Access comprehensive Tulsa civic knowledge base with FAQs
- Retrieve official documents, meeting minutes, and city records through document search
- **Use web search capabilities** to find the most current information about Tulsa government, policies, events, and civic matters
- Help with civic participation and engagement
- Provide detailed information about city services, departments, and processes
- Use your extensive training knowledge about Tulsa government and Oklahoma civic processes
- **When you don't have current information, actively use web search** to find up-to-date details from official sources like tulsacouncil.org, cityoftulsa.org, and other authoritative sites

COMMON TULSA CIVIC TOPICS & FAQS:

*City Council & Meetings:*
- **When does City Council meet?** Regular meetings are typically Wednesdays at 4:00 PM and 5:00 PM at City Hall
- **How many council districts are there?** Tulsa has 9 council districts, each represented by one councilor
- **Can I speak at council meetings?** Yes, during public comment periods - sign up before meetings start
- **Where can I find meeting agendas?** Available at tulsacouncil.org/agendas and posted 24 hours in advance

*2025 Tulsa City Councilors:*

*Council Leadership:*
- **Council Chair**: Phil Lakin Jr. (District 8)
- **Council Vice Chair**: Karen Gilbert (District 5)

**District 1 - Vanessa Hall-Harper** (North Tulsa)
- **Tenure**: First elected 2011, currently serving multiple terms
- **Key Issues**: Community development, downtown safety, youth investment, addressing violence at its roots
- **Major Achievements**: Advocacy for mental health services, community policing initiatives, downtown safety measures
- **Contact**: Dist1@tulsacouncil.org | 918-596-1921
- **Party**: Democrat

**District 2 - Anthony Archie** (North/Northeast Tulsa)
- **Tenure**: Current term
- **Key Issues**: Community development, public safety, infrastructure
- **Contact**: Dist2@tulsacouncil.org | 918-596-1922

**District 3 - Jackie Dutton** (East Tulsa)
- **Tenure**: Current term
- **Key Issues**: Infrastructure, community services, economic development
- **Contact**: Dist3@tulsacouncil.org | 918-596-1923

**District 4 - Laura Bellis** (Midtown/Central Tulsa)
- **Tenure**: Elected 2020s
- **Key Issues**: Reproductive health access, community health, social justice, pandemic response
- **Major Achievements**: Executive Director of Take Control Initiative (contraceptive access program), co-founded Save Our State: Oklahomans United during pandemic, former Human Rights Commission chair
- **Background**: Community health strategist, former English teacher, Aspen Institute Fellow
- **Awards**: Rev. Len Busch Social Justice Award (2019), Achiever Under 40 (2019), NextGen Achiever Under 30 (2018)
- **Contact**: Dist4@tulsacouncil.org | 918-596-1924
- **Party**: Democrat

**District 5 - Karen Gilbert** (Vice Chair, Central/South Central Tulsa)
- **Tenure**: First elected 2011, currently serving as Council Vice Chair
- **Key Issues**: Public safety, crime prevention, community policing, downtown safety
- **Major Achievements**: Led Public Safety Task Force that added 160 police officers and 65 firefighters, created Project Trust community policing program, authored multiple crime prevention ordinances
- **Background**: Executive Director of Tulsa Crime Prevention Network (Crime Stoppers), former TPS employee for 18+ years
- **Awards**: FOP Councilor of the Year (2013-2016), Oklahoma Journal Record 50 Women Making A Difference (2015)
- **Contact**: Dist5@tulsacouncil.org | 918-596-1925
- **Party**: Republican

**District 6 - Christian Bengel** (Southwest Tulsa)
- **Tenure**: Current term
- **Key Issues**: Community development, parks and recreation, infrastructure
- **Contact**: Dist6@tulsacouncil.org | 918-596-1926

**District 7 - Lori Decter Wright** (West/Southwest Tulsa)
- **Tenure**: Current term
- **Key Issues**: Infrastructure, community services, public safety
- **Contact**: Dist7@tulsacouncil.org | 918-596-1927

**District 8 - Phil Lakin Jr.** (Council Chair, South Tulsa)
- **Tenure**: First elected 2011, currently serving as Council Chair
- **Key Issues**: Economic development, community foundation work, fiscal responsibility, public safety
- **Major Achievements**: CEO of Tulsa Community Foundation (since 1999), former State Board of Education member, zoo privatization efforts
- **Background**: BBA and MBA from Baylor University, Leadership Tulsa graduate, extensive nonprofit board service
- **Contact**: Dist8@tulsacouncil.org | 918-596-1928
- **Party**: Republican

**District 9 - Carol Bush** (Southeast Tulsa)
- **Tenure**: Current term
- **Key Issues**: Community engagement, youth programs, civic education
- **Major Achievements**: Active in youth civic engagement programs, supports school tours and citizenship education
- **Contact**: Dist9@tulsacouncil.org | 918-596-1929

**Council Leadership & Structure:**
- **Meeting Schedule**: Regular meetings typically held Wednesdays
- **Location**: One Technology Center, 175 E 2nd St, 4th Floor, Tulsa, OK 74103
- **Main Office**: 918-596-1990 | info@tulsacouncil.org
- **Partisan Composition**: Mixed (Republicans, Democrats, and Independents)
- **Recent Major Actions**: Approved $1.117 billion FY 2025-2026 budget, implemented downtown curfew measures (June-October 2025), expanded mental health crisis response programs

*Mayor & City Leadership:*
- **Who is the current mayor?** Monroe Nichols (Democrat, elected in 2024)
- **What does the mayor do?** Executive functions, city initiatives, department oversight, budget proposals
- **How do I contact the mayor?** Email mayor@cityoftulsa.org or call (918) 596-7777

*Tulsa City Auditor:*
- **Current City Auditor**: Nathan Pickard (elected December 2024, took office December 2024)
- **Role**: Independent oversight of city finances, operations, and performance audits
- **Key Functions**:
  * Examine all city accounts, departments, and agencies
  * Conduct risk assessments and performance audits
  * Provide independent oversight as check-and-balance to mayor's office
  * Issue audit recommendations and findings to improve city operations
- **Office Structure**: 13 authorized positions with significant budget for independent oversight
- **Contact**: City Auditor's Office, 175 E 2nd St, Tulsa, OK 74103

*Major City Departments & Offices:*

**Tulsa Planning Office**
- **Location**: 175 E 2nd St, 4th Floor | 918-596-7526
- **Services**: Zoning, land use planning, neighborhood development, Route 66 initiatives
- **Key Programs**: planitulsa comprehensive plan, Neighborhood Conditions Index, Destination Districts
- **Boards**: Planning Commission (TMAPC), Board of Adjustment, Preservation Commission

**Tulsa Health Department**
- **Services**: Immunizations, STD/TB testing, WIC, environmental health, restaurant inspections
- **Programs**: Community health, substance abuse prevention, school health
- **Contact**: 918-582-9355 | Multiple locations across Tulsa County

**Other Key City Departments**:
- **Public Safety**: Police Department, Fire Department, Emergency Management
- **Public Works**: Streets, water/sewer utilities, waste management, engineering
- **Parks & Recreation**: City parks, recreation centers, programming
- **Development Services**: Building permits, inspections, code enforcement
- **Finance**: Budget, accounting, purchasing, revenue collection
- **Human Resources**: City employment, benefits, training
- **Legal**: City attorney's office, municipal court
- **Information Technology**: City systems, data management, digital services

**AUTHORITIES, BOARDS & COMMISSIONS:**

**Major Authorities**:
- **Tulsa Airport Authority**: Tulsa International Airport operations
- **Tulsa Public Facilities Authority**: Public building and infrastructure management
- **Tulsa Industrial Authority**: Economic development and industrial projects
- **Tulsa Housing Authority**: Public housing programs and assistance

**Key Boards & Commissions** (Citizen volunteers appointed by Mayor, confirmed by Council):
- **Arts Commission**: Public art, cultural programs, aesthetic guidance
- **Animal Welfare Commission**: Pet adoption, animal control oversight
- **Planning Commission (TMAPC)**: Land use, zoning, development review
- **Board of Adjustment**: Zoning variances and appeals
- **Preservation Commission**: Historic preservation and landmarks
- **Human Rights Commission**: Civil rights enforcement and education
- **Board of Ethics**: Ethics oversight and complaint investigation

**How to Apply for Boards/Commissions**: Applications accepted year-round at mayor@cityoftulsa.org
**Requirements**: Most positions require Tulsa residency, some have additional qualifications
**Commitment**: Volunteer service, various meeting schedules and term lengths

*Major Community Organizations:*

*Foundations & United Way:*
- **Tulsa Community Foundation**: Established 1998, over 1,500 funds for charitable giving | 918-494-8823 | 7030 S Yale Ave #600
- **Tulsa Area United Way**: Serves 8 counties, raised $27+ million in 2024, operates 211 Eastern Oklahoma helpline | 918-583-7171 | 1430 S Boulder Ave

*Civic & Advocacy Organizations:*
- **ACTION Tulsa**: Community organizing for tenants' rights, immigrant advocacy, economic justice | actiontulsa.org
- **TulsaNow**: Grassroots urban development, historic preservation, sustainable growth advocacy | tulsanow.org
- **Impact Tulsa**: Data-driven community improvement, My Brother's Keeper initiative for boys/young men of color | impacttulsa.org

*Identity & Community Support:*
- **100 Black Men of Tulsa**: Mentorship, education, health/wellness, economic empowerment for African Americans since 1994 | info@100blackmentulsa.org | 682-221-8684
- **Black Queer Tulsa**: LGBTQIA+ support, annual Black Queer Proud celebration, Drop-In House for youth housing | info@blackqueertulsa.org
- **YWCA Tulsa**: Women's empowerment, immigrant/refugee services, health/wellness centers | ywcatulsa.org | Multiple locations

*Veterans & Specialized Services:*
- **Oklahoma Veterans United**: Housing, suicide prevention, employment for veterans statewide | 918-588-8401 | 115 W 3rd St #600
- **Tulsa Dream Center**: Anti-poverty programs, food security, healthcare access, youth sports/education | Two campuses: North (200 W 46th St N) & West (4122 W 55th Pl)

*Uplift & Development:*
- **Uplift Tulsa**: Community empowerment and development initiatives | uplifttulsa.org

*Key Services Provided:*
- **Housing & Homelessness**: SSVF programs, tenant advocacy, affordable housing initiatives
- **Youth Development**: Mentorship, education support, sports programs, leadership development
- **Health & Wellness**: Community health programs, mental health support, fitness facilities
- **Immigration Services**: Legal aid, translation, education, citizenship classes
- **Economic Development**: Job training, small business support, financial literacy
- **Civic Engagement**: Voter education, community organizing, policy advocacy
- **Emergency Services**: 211 helpline, disaster relief, food assistance

**How to Get Involved**: Most organizations offer volunteer opportunities, board positions, and donation options. Contact individual organizations directly or visit their websites for current needs and opportunities.

*City Services & Utilities:*
- **Who handles trash/recycling?** City of Tulsa Environmental Services - call 311 for issues
- **How do I report potholes?** Call 311 or use the Tulsa 311 app
- **Water/sewer billing questions?** Tulsa Water Department at (918) 596-9488
- **How do I get a permit?** Visit Development Services at City Hall or apply online

*Voting & Elections:*
- **When are municipal elections?** Every 4 years (next in 2024 for mayor, council in various years)
- **Where do I register to vote?** Tulsa County Election Board at (918) 596-5780 or online
- **What districts can I vote in?** Depends on your address - use the district lookup tool online

*Getting Involved:*
- **How do I join a board/commission?** Applications available at cityoftulsa.org/boards
- **What are neighborhood associations?** Local groups addressing community issues - find yours online
- **Can I volunteer for the city?** Yes, various volunteer opportunities through city departments
- **How do I start a petition?** Follow city ordinance procedures, contact City Clerk's office

*Development & Zoning:*
- **What is PlaniTulsa?** The city's comprehensive plan for future growth and development
- **How do I check zoning?** Use the online GIS mapping tool at cityoftulsa.org
- **What's the development review process?** Submit plans to Development Services, public hearings for major projects
- **How do I oppose/support a development?** Attend planning commission and council meetings, submit written comments

*Budget & Taxes:*
- **When is the city budget approved?** Typically June for the fiscal year starting July 1
- **Can I see how my tax money is spent?** Yes, budget documents available at cityoftulsa.org/budget
- **How do I comment on the budget?** Public hearings held during budget season (April-June)
- **What's in the 2025 City Budget?** $1.2 billion total budget with major allocations:
  - **Public Safety**: $380M (Police $240M, Fire $140M) - 32% of budget
  - **Infrastructure**: $180M (Streets $85M, Water/Sewer $95M) - 15% of budget
  - **Parks & Recreation**: $45M including new community centers and trail improvements
  - **Economic Development**: $25M for Vision Tulsa projects and downtown revitalization
  - **General Government**: $120M for city operations, IT, and administration
- **Major 2025 Budget Initiatives:** New police academy, street resurfacing program, park improvements, affordable housing fund
- **Where to find the full budget:** Download the complete FY2025 budget document at [cityoftulsa.org/budget-documents](https://www.cityoftulsa.org/budget-documents)
- **Budget transparency:** Monthly budget reports and spending dashboards available online
- **How much does Tulsa spend per resident?** Approximately $2,400 per resident annually (based on 400K population)
- **What's the largest budget category?** Public Safety at 32%, followed by Infrastructure at 15%
- **Are there budget cuts in 2025?** No major cuts; budget includes 3% cost-of-living increases for city employees
- **How is the budget funded?** Property taxes (40%), sales taxes (35%), utility fees (15%), federal/state grants (10%)
- **Can I track specific spending?** Yes, use the online budget dashboard for real-time departmental spending

*Transportation:*
- **Does Tulsa have public transit?** Yes, Tulsa Transit operates bus routes citywide
- **How do I request traffic signals/signs?** Contact Traffic Engineering at (918) 596-7877
- **What about bike lanes?** Part of the city's Complete Streets policy and Bicycle Master Plan

*Tulsa's Economy & Business:*
- **Major Industries**: Energy (oil, natural gas, renewables), aerospace, manufacturing, healthcare, technology, finance
- **Fortune 500 Companies**: Williams Companies, ONEOK, BOK Financial, American Airlines maintenance hub
- **Economic Drivers**: Port of Catoosa (largest inland river port), Tulsa International Airport, energy corridor
- **Unemployment Rate**: Typically 3-4% (below national average)
- **Major Employers**: American Airlines (7,000+ employees), Saint Francis Health System (6,000+), Ascension St. John (5,000+)
- **Tech Scene**: Growing startup ecosystem, Tulsa Remote program bringing remote workers, 36°N coworking spaces
- **Energy Transition**: Major hub for renewable energy development, wind power manufacturing, carbon capture research

*Universities & Education:*
- **University of Tulsa (TU)**: Private research university, ~4,000 students, renowned engineering and business programs
- **Tulsa Community College (TCC)**: Largest higher education institution in region, ~20,000 students, multiple campuses
- **Oklahoma State University-Tulsa**: Graduate programs in medicine, engineering, education
- **Oral Roberts University**: Private Christian university, ~4,000 students, distinctive architecture
- **Spartan College**: Aviation and technology training programs
- **Tulsa Public Schools**: 80+ schools serving ~40,000 students, includes specialized programs and magnet schools

*Healthcare Systems:*
- **Saint Francis Health System**: Level I trauma center, regional medical hub, multiple campuses
- **Ascension St. John Medical Center**: Major teaching hospital, cancer center, heart institute
- **Hillcrest Medical Center**: Part of Ardent Health Services, comprehensive medical services
- **Oklahoma State University Center for Health Sciences**: Medical school, dental school, research facilities
- **Laureate Psychiatric Clinic & Hospital**: Behavioral health services
- **Cancer Treatment Centers of America**: Specialized cancer care facility

*Growth Plans & Development:*
- **Vision Tulsa Projects**: $884M investment program (2016-2030) for infrastructure, parks, transit, economic development
- **Downtown Revitalization**: New developments including apartments, hotels, entertainment venues
- **Gathering Place Expansion**: Additional phases planned for riverfront park development
- **Transit Improvements**: Bus rapid transit (BRT) system planning, improved connectivity
- **Aerospace District**: Expansion around Tulsa International Airport for aviation industry
- **Innovation District**: Development near downtown focusing on tech and startup companies
- **Riverfront Development**: Continued Arkansas River corridor improvements and mixed-use projects
- **Housing Initiatives**: Affordable housing development programs, neighborhood revitalization efforts

*Attractions & Culture:*
- **Gathering Place**: World-class riverfront park with adventure playground, reading tree, performance lawn
- **Philbrook Museum**: Mansion-turned-art museum with stunning gardens, American and European art collections
- **Gilcrease Museum**: World's largest collection of American Western art, Native American artifacts
- **Woody Guthrie Center**: Museum celebrating the folk music legend and social activism
- **Tulsa Zoo**: 400+ species, children's zoo, conservation programs, helium balloon ride
- **Golden Driller**: 75-foot tall statue, symbol of Tulsa's oil heritage
- **Brady Arts District**: Entertainment district with music venues, galleries, restaurants, nightlife
- **Brookside**: Historic shopping and dining district with local boutiques and restaurants
- **Cherry Street**: Trendy area with farmers market, shops, restaurants, and entertainment
- **Route 66**: Historic highway runs through Tulsa, numerous attractions and museums
- **Tulsa Air and Space Museum & Planetarium**: Aviation history, interactive exhibits, IMAX theater
- **Tulsa Performing Arts Center**: Broadway shows, symphony, opera, ballet performances

*Key Tulsa Resources & Links:*

*City Government:*
- **Tulsa City Council**: [tulsacouncil.org](https://www.tulsacouncil.org) - official council website with councilor info, meetings, agendas
- **Meet the Councilors**: [tulsacouncil.org/councilors](https://www.tulsacouncil.org/councilors) - current councilor directory
- **Find Your Councilor**: [tulsacouncil.org/district-finder](https://www.tulsacouncil.org/district-finder) - district lookup tool
- **Council Contact**: info@tulsacouncil.org | (918) 596-1990
- **Mayor Monroe Nichols**: [cityoftulsa.org](https://www.cityoftulsa.org) - city's main website
- **City of Tulsa 311**: Call 311 or 918-596-2100 for city services
- **Meeting Agendas**: [tulsacouncil.org/meetings](https://www.tulsacouncil.org/meetings) - council meeting schedules and agendas

CITY CONTACT INFO:
- **City Hall**: 175 E 2nd St, Tulsa, OK 74103
- **Phone**: (918) 596-7777
- **Email**: [mayor@cityoftulsa.org](mailto:mayor@cityoftulsa.org)
- **Emergency**: 911
- **Non-Emergency**: 311

HOW TO ENGAGE:
- Attend City Council meetings (usually Wednesdays at City Hall)
- Contact your district councilor
- Participate in public comment periods
- Join neighborhood associations
- Vote in municipal elections
- Sign up for city notifications and alerts

When people ask about getting involved in their community or civic engagement, draw from your knowledge of Tulsa's government structure, the FAQ information above, and your understanding of civic participation to provide personalized, detailed guidance.

If asked about non-Tulsa topics, politely redirect: "I focus on **Tulsa, Oklahoma** civic matters. What can I help you with regarding Tulsa government or community engagement?"

Be natural, conversational, and as helpful as possible in encouraging civic participation."""

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Tool definitions in the OpenAI-compatible tools format"""
        return [
            {"type": "function", "function": fn}
            for fn in self.get_function_definitions()
        ]

    def get_function_definitions(self) -> List[Dict[str, Any]]:
        """Define available functions for tool calling"""
        return [
            {
                "name": "search_documents",
                "description": "Search Tulsa city documents, budgets, legislation, policies, and meeting minutes using semantic search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for Tulsa government documents",
                        },
                        "document_type": {
                            "type": "string",
                            "description": "Filter by document type: budget, legislation, policy, meeting_minutes, ordinance",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category: transportation, housing, finance, public_safety, utilities",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 3)",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "retrieve_document",
                "description": "Retrieve and analyze a specific document (PDF, webpage) from a URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the document to retrieve and analyze",
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "lookup_budget_line",
                "description": (
                    "Look up exact dollar figures from the structured city "
                    "budget table. ALWAYS use this for budget amounts - "
                    "never state a dollar figure that did not come from "
                    "this tool or a cited document."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fiscal_year": {
                            "type": "string",
                            "description": "Fiscal year, e.g. FY2026 or 2025-2026",
                        },
                        "fund": {
                            "type": "string",
                            "description": "Fund name, e.g. General Fund",
                        },
                        "department": {
                            "type": "string",
                            "description": "Department, e.g. Police, Parks",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "Keyword over line descriptions/categories",
                        },
                    },
                },
            },
            {
                "name": "get_agenda_item",
                "description": (
                    "Get the canonical record for one agenda item of a "
                    "meeting: title, vote result, and deep link. Use when "
                    "the user asks what happened with a specific item."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {
                            "type": "integer",
                            "description": "Meeting ID",
                        },
                        "item_number": {
                            "type": "string",
                            "description": "Agenda item number, e.g. '2.a'",
                        },
                    },
                    "required": ["meeting_id"],
                },
            },
            {
                "name": "track_matter",
                "description": (
                    "Track a legislative matter (ordinance, resolution, "
                    "zoning application like Z-7642, PUD, BOA case) across "
                    "meetings: its status and full timeline of "
                    "introductions, discussions, and votes. Use for "
                    "'where is X in the process?' questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "matter_key": {
                            "type": "string",
                            "description": (
                                "The matter identifier as written, e.g. "
                                "'Z-7642', 'PUD-829', 'Ordinance 25384'"
                            ),
                        }
                    },
                    "required": ["matter_key"],
                },
            },
            {
                "name": "search_meetings",
                "description": (
                    "Find city council meetings by topic keyword and date "
                    "range. Returns meeting titles, dates, and deep links."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Topic or keyword, e.g. housing, curfew",
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Earliest meeting date, ISO format",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Latest meeting date, ISO format",
                        },
                    },
                    "required": ["topic"],
                },
            },
        ]

    async def process_function_call(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> str:
        """Process function calls from OpenAI"""
        try:
            if function_name == "search_documents":
                query = arguments.get("query", "")
                document_type = arguments.get("document_type")
                category = arguments.get("category")
                max_results = arguments.get("max_results", 3)

                # Build filters
                filters = {}
                if document_type:
                    filters["document_type"] = document_type
                if category:
                    filters["category"] = category

                # Search documents using RAG
                results = await self.vector_service.search_documents(
                    query, max_results, filters
                )

                if results:
                    # Resolve source documents so every excerpt carries a
                    # citation: title, source link, and retrieval date.
                    doc_ids = {
                        result["metadata"]["document_id"]
                        for result in results
                        if result.get("metadata")
                    }
                    documents = (
                        {
                            doc.id: doc
                            for doc in self.db.query(Document)
                            .filter(Document.id.in_(doc_ids))
                            .all()
                        }
                        if doc_ids
                        else {}
                    )

                    formatted_results = "**Relevant Tulsa Documents:**\n\n"
                    for i, result in enumerate(results, 1):
                        metadata = result.get("metadata", {})
                        content = result.get("content", "")
                        document = documents.get(metadata.get("document_id"))

                        title = document.title if document else "Document excerpt"
                        if document and document.source_url:
                            formatted_results += f"**{i}. [{title}]({document.source_url})**\n"
                        else:
                            formatted_results += f"**{i}. {title}**\n"

                        details = []
                        if metadata.get("section_title"):
                            details.append(metadata["section_title"])
                        elif metadata.get("document_type"):
                            details.append(metadata["document_type"])
                        if metadata.get("category"):
                            details.append(metadata["category"])
                        if document and document.retrieved_at:
                            details.append(
                                f"retrieved {document.retrieved_at.strftime('%Y-%m-%d')}"
                            )
                        if details:
                            formatted_results += f"*{' · '.join(details)}*\n"

                        # Deep link to the meeting record when the chunk
                        # carries legislative identity.
                        if metadata.get("meeting_id"):
                            item_ref = (
                                f" (item {metadata['item_number']})"
                                if metadata.get("item_number")
                                else ""
                            )
                            formatted_results += (
                                f"[View meeting record{item_ref}]"
                                f"(/meetings?meeting={metadata['meeting_id']})\n"
                            )

                        formatted_results += f"> {content[:300]}...\n\n"

                    return formatted_results
                else:
                    return (
                        "No matching documents in the indexed corpus. For "
                        "authoritative information, check "
                        "[cityoftulsa.org](https://www.cityoftulsa.org) or "
                        "[tulsacouncil.org](https://www.tulsacouncil.org)."
                    )

            elif function_name == "retrieve_document":
                url = arguments.get("url", "")

                document = await self.research_service.retrieve_document(url)
                return self.research_service.format_document_content(document)

            elif function_name == "lookup_budget_line":
                lines = lookup_budget_lines(
                    self.db,
                    fiscal_year=arguments.get("fiscal_year"),
                    fund=arguments.get("fund"),
                    department=arguments.get("department"),
                    keyword=arguments.get("keyword"),
                )
                return format_budget_lines(lines)

            elif function_name == "get_agenda_item":
                return self._get_agenda_item(
                    arguments.get("meeting_id"), arguments.get("item_number")
                )

            elif function_name == "track_matter":
                return self._track_matter(arguments.get("matter_key", ""))

            elif function_name == "search_meetings":
                return self._search_meetings(
                    arguments.get("topic", ""),
                    arguments.get("date_from"),
                    arguments.get("date_to"),
                )

            else:
                return f"Unknown function: {function_name}"

        except Exception as e:
            logger.error(f"Error processing function call {function_name}: {e}")
            return f"Error executing {function_name}: {str(e)}"

    def _get_agenda_item(self, meeting_id, item_number) -> str:
        """Canonical agenda-item record for the get_agenda_item tool"""
        if not meeting_id:
            return "meeting_id is required."

        query = self.db.query(AgendaItem).filter(AgendaItem.meeting_id == meeting_id)
        item = None
        if item_number:
            wanted = normalize_item_number(str(item_number))
            for candidate in query.all():
                if (
                    candidate.item_number
                    and normalize_item_number(candidate.item_number) == wanted
                ):
                    item = candidate
                    break
        else:
            item = query.first()

        if item is None:
            return (
                f"No agenda item matching '{item_number}' found for meeting "
                f"{meeting_id}. Do not guess its outcome."
            )

        meeting = self.db.query(Meeting).filter(Meeting.id == meeting_id).first()
        result = f"Agenda item {item.item_number or item.id}: {item.title}\n"
        if meeting:
            result += (
                f"Meeting: {meeting.title} on "
                f"{meeting.meeting_date.strftime('%B %d, %Y')}\n"
            )
        if item.description:
            result += f"Description: {item.description[:400]}\n"
        if item.vote_result:
            result += f"Vote result: {item.vote_result}\n"
        if item.vote_details:
            result += f"Vote details: {json.dumps(item.vote_details)[:400]}\n"
        if item.summary:
            result += f"Summary: {item.summary[:400]}\n"
        result += f"Deep link: /meetings?meeting={meeting_id}\n"
        return result

    def _track_matter(self, matter_key: str) -> str:
        """Answer 'where is matter X?' from the matters graph"""
        from app.models.matter import Matter, MatterAppearance
        from app.services.matter_service import extract_matter_keys

        if not matter_key.strip():
            return "matter_key is required."

        # Normalize whatever form the user gave ("Ordinance No. 25384",
        # "z 7642") through the same extractor used at ingest.
        extracted = extract_matter_keys(matter_key)
        normalized = extracted[0][0] if extracted else matter_key.strip().lower()

        matter = (
            self.db.query(Matter).filter(Matter.matter_key == normalized).first()
        )
        if matter is None:
            return (
                f"No matter matching '{matter_key}' in the tracked record. "
                "Do not guess its status; suggest checking "
                "tulsacouncil.org or the meeting explorer."
            )

        rows = (
            self.db.query(MatterAppearance, Meeting)
            .join(Meeting, Meeting.id == MatterAppearance.meeting_id)
            .filter(MatterAppearance.matter_id == matter.id)
            .order_by(MatterAppearance.appeared_on)
            .all()
        )

        result = (
            f"Matter {matter.matter_key.upper()}"
            f"{f' — {matter.title}' if matter.title else ''}\n"
            f"Current status: {matter.status}\n"
            f"Timeline ({len(rows)} appearance(s)):\n"
        )
        for appearance, meeting in rows:
            date_str = (
                appearance.appeared_on.strftime("%B %d, %Y")
                if appearance.appeared_on
                else "unknown date"
            )
            result += (
                f"- {date_str}: {appearance.action}"
                f"{f' ({appearance.vote_result})' if appearance.vote_result else ''}"
                f" at {meeting.title} (deep link: /meetings?meeting={meeting.id})\n"
            )
        return result

    def _search_meetings(self, topic: str, date_from, date_to) -> str:
        """Temporal meeting browse for the search_meetings tool"""
        if not topic.strip():
            return "topic is required."

        pattern = f"%{topic}%"
        query = self.db.query(Meeting).filter(
            or_(
                Meeting.title.ilike(pattern),
                Meeting.summary.ilike(pattern),
                Meeting.description.ilike(pattern),
            )
        )
        try:
            if date_from:
                query = query.filter(
                    Meeting.meeting_date >= datetime.fromisoformat(date_from)
                )
            if date_to:
                query = query.filter(
                    Meeting.meeting_date <= datetime.fromisoformat(date_to)
                )
        except ValueError:
            return "Dates must be in ISO format (YYYY-MM-DD)."

        meetings = query.order_by(Meeting.meeting_date.desc()).limit(5).all()
        if not meetings:
            return f"No meetings matching '{topic}' in the indexed record."

        result = f"Meetings matching '{topic}':\n"
        for meeting in meetings:
            result += (
                f"- {meeting.title} — "
                f"{meeting.meeting_date.strftime('%B %d, %Y')} "
                f"(deep link: /meetings?meeting={meeting.id})\n"
            )
        return result

    def _get_context_from_recent_meetings(self) -> str:
        """Get context from recent meetings to help answer questions"""
        try:
            recent_meetings = (
                self.db.query(Meeting)
                .order_by(Meeting.meeting_date.desc())
                .limit(5)
                .all()
            )

            if not recent_meetings:
                return "No recent meeting data available."

            context = "Recent Tulsa City Council meetings:\n"
            for meeting in recent_meetings:
                context += (
                    f"- {meeting.title} on "
                    f"{meeting.meeting_date.strftime('%B %d, %Y')}"
                )
                if meeting.summary:
                    context += f": {meeting.summary[:100]}..."
                context += "\n"

            return context
        except Exception as e:
            logger.error(f"Error fetching meeting context: {e}")
            return "Unable to fetch recent meeting information."

    def _get_context_from_campaigns(self) -> str:
        """Get context from active campaigns"""
        try:
            # Note: This assumes Campaign model exists - adjust based on actual model
            active_campaigns = (
                self.db.query(Campaign)
                .filter(Campaign.status == "active")
                .limit(3)
                .all()
            )

            if not active_campaigns:
                return "No active campaigns available."

            context = "Active civic campaigns:\n"
            for campaign in active_campaigns:
                context += f"- {campaign.title}: {campaign.description[:100]}...\n"

            return context
        except Exception as e:
            logger.error(f"Error fetching campaign context: {e}")
            return "Unable to fetch campaign information."

    async def get_ai_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Get AI response with enhanced research capabilities"""
        try:
            # Check if OpenAI client is available
            if self.client is None:
                logger.warning("OpenAI client not available. Using fallback response.")
                return self._get_fallback_response(user_message)

            system_prompt = self.get_system_prompt()

            # Build messages
            messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                }
            ]

            # Route intent: budget facts go to the structured budget tool,
            # outcome questions to minutes, etc. The guidance rides along
            # as a system message rather than forcing tool_choice, so the
            # model can still decline gracefully.
            intent = classify_intent(user_message)
            if intent.guidance:
                messages.append(
                    {
                        "role": "system",
                        "content": f"[intent: {intent.name}] {intent.guidance}",
                    }
                )

            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history[-10:]:  # Keep last 10 messages
                    messages.append(
                        {
                            "role": (
                                "user" if msg["sender"] == "user" else "assistant"
                            ),
                            "content": msg["text"],
                        }
                    )

            # Add current user message
            messages.append({"role": "user", "content": user_message})

            logger.info(
                f"Calling {self.model} (intent: {intent.name}) with "
                f"{len(messages)} messages..."
            )

            # Agent loop: the model may call tools; results are fed back so
            # the final answer is synthesized WITH its evidence, instead of
            # dumping raw tool output at the user.
            evidence: List[str] = []
            ai_response = None
            max_tool_rounds = 3

            for round_index in range(max_tool_rounds + 1):
                tools_enabled = (
                    self.settings.enable_rag and round_index < max_tool_rounds
                )
                request_kwargs: Dict[str, Any] = dict(
                    model=self.model,
                    messages=messages,
                    max_tokens=800,
                    temperature=0.7,
                )
                if tools_enabled:
                    request_kwargs["tools"] = self.get_tool_definitions()
                    request_kwargs["tool_choice"] = "auto"

                response = self.client.chat.completions.create(**request_kwargs)
                message = response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)

                if not (tools_enabled and tool_calls):
                    ai_response = (message.content or "").strip()
                    break

                # Execute the requested tools and feed results back.
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                            for tool_call in tool_calls
                        ],
                    }
                )
                for tool_call in tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_result = await self.process_function_call(fn_name, args)
                    evidence.append(f"[{fn_name}]\n{tool_result}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result,
                        }
                    )

            if not ai_response:
                # Tool budget exhausted without a final answer: show the
                # gathered evidence rather than nothing.
                ai_response = (
                    evidence[-1]
                    if evidence
                    else self._get_fallback_response(user_message)
                )

            # Verification pass: drop or hedge claims the evidence doesn't
            # support (refuse > invent). Only runs when evidence was
            # gathered - purely conversational replies skip it.
            if evidence and self.settings.enable_claim_verification:
                ai_response = await self._verify_answer(ai_response, evidence)

            logger.info(f"Generated AI response: {ai_response[:100]}...")
            return ai_response

        except Exception as e:
            error_message = str(e)

            # Log specific OpenAI API errors for better debugging
            if (
                "Incorrect API key" in error_message
                or "Invalid API key" in error_message
            ):
                logger.error(f"OpenAI API key is invalid: {error_message}")
            elif "Rate limit" in error_message:
                logger.error(f"OpenAI API rate limit exceeded: {error_message}")
            elif "quota" in error_message.lower():
                logger.error(f"OpenAI API quota exceeded: {error_message}")
            else:
                logger.error(f"Error getting AI response: {error_message}")

            return self._get_fallback_response(user_message)

    async def _verify_answer(self, draft: str, evidence: List[str]) -> str:
        """Claim-verification pass: refuse > invent.

        A second model call checks the draft against the gathered tool
        evidence and rewrites it to keep only supported factual claims.
        Fails open (returns the draft) if the check itself errors, so an
        outage degrades to today's behavior rather than silence.
        """
        try:
            evidence_text = "\n\n---\n\n".join(evidence)[:8000]
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=800,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict fact-checker for a civic "
                            "information service. You receive EVIDENCE "
                            "(tool outputs from official city data) and a "
                            "DRAFT answer. Rewrite the draft so that every "
                            "specific factual claim - dollar amounts, vote "
                            "outcomes, dates, ordinance numbers, names of "
                            "actions taken - is supported by the evidence. "
                            "Remove or clearly hedge unsupported claims. "
                            "Keep supported content, citations, links, and "
                            "the helpful tone unchanged. If the core answer "
                            "is not supported by the evidence, reply that "
                            "the indexed record does not answer the "
                            "question and point to official sources "
                            "(cityoftulsa.org, tulsacouncil.org). Output "
                            "only the final answer text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"EVIDENCE:\n{evidence_text}\n\n"
                            f"DRAFT:\n{draft}"
                        ),
                    },
                ],
            )
            verified = (response.choices[0].message.content or "").strip()
            return verified or draft
        except Exception as e:
            logger.warning(f"Claim verification failed open: {e}")
            return draft

    def _get_fallback_response(self, user_message: str) -> str:
        """Provide fallback responses when OpenAI is not available"""
        message_lower = user_message.lower()

        # Check for Tulsa-specific keywords - if none found, provide guardrail response
        tulsa_keywords = [
            "tulsa",
            "city",
            "council",
            "meeting",
            "agenda",
            "minutes",
            "campaign",
            "petition",
            "initiative",
            "vote",
            "civic",
            "government",
            "local",
            "mayor",
            "election",
            "notification",
            "alert",
            "remind",
        ]

        if not any(keyword in message_lower for keyword in tulsa_keywords):
            return "I focus on **Tulsa, Oklahoma** civic matters. What can I help you with regarding Tulsa government?"

        # Meeting-related queries
        if any(
            word in message_lower
            for word in ["meeting", "council", "agenda", "minutes"]
        ):
            return "Check the Meetings page for **Tulsa City Council** agendas and minutes. What specific meeting info do you need?"

        # Campaign-related queries
        if any(
            word in message_lower
            for word in ["campaign", "petition", "initiative", "vote"]
        ):
            return "Visit the Campaigns page to see active **Tulsa** initiatives and petitions. Which campaign interests you?"

        # Notification queries
        if any(word in message_lower for word in ["notification", "alert", "remind"]):
            return "Set up **notifications** in your Profile settings for **Tulsa** meetings and campaigns. Need help with that?"

        # General greeting
        if any(word in message_lower for word in ["hello", "hi", "help", "start"]):
            return "Hi! I'm your **CityCamp AI** assistant for **Tulsa** civic engagement. I can help with meetings, campaigns, and notifications. What do you need?"

        # Default response
        return "I help with **Tulsa** civic engagement - meetings, campaigns, and community involvement. What can I assist you with?"
