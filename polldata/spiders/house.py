import re
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.contrib.spiders import CrawlSpider, Rule
from scrapy.http import Request
from scrapy.selector import HtmlXPathSelector
from scrapy.item import Item
from scrapy import log

from polldata.items import HousePollItem
from polldata.utils import parsePollData
from polldata.linkextractors.rcp_regex import RCP_RegexLinkExtractor

class HouseSpider(CrawlSpider):
    name = "house2012"
    allowed_domains = ["realclearpolitics.com"]
    start_urls = [
            "http://www.realclearpolitics.com/epolls/2012/house/2012_elections_house_map.html",
    ]
    fields_to_export = ['service', 'end', 'sample', 'voters', 'dem', 'rep', 'ind']

    rules = (
        Rule(
            SgmlLinkExtractor(
                allow=(r"epolls/2012/house/[a-z]{2}/[a-z_]+-[0-9]{4}\.html"),
                # Regex explanation:
                #     [a-z]{2} - matches a two character state abbreviation
                #     [a-z]*   - matches a state name and race info
                #     [0-9]{4} - matches a 4 number unique webpage identifier

                allow_domains=('realclearpolitics.com',),
            ),
            callback='parseStatePolls',
            # follow=None, # default 
            process_links='processLinks',
            process_request='processRequest',
        ),
    )
    def parseStatePolls(self, response):
        """Find pollitems for a state.

        For every poll in this state: find the poll's data and process it into
        a pollitem.

        Args:
            response
                An html response that contains the presidential polling data for a state.

        Returns:
            A list of pollitems that each represent a unique state-level poll.
        """
        items = []
        hxs = HtmlXPathSelector(response)

        lookup = self._getDataPositions( hxs.select('//*[@id="polling-data-full"]/table/tr[1]/th/text()').extract() )

        title = hxs.select('//*[@id="main-poll-title"]/text()').extract()[0].split(':')[0]
        district = ''
        if 'At-Large' in title:
            district = 'AL'
        else:
            district = re.findall(r'\d+', state)[0]            
        state = hxs.select('//*[@id="snapshot"]/h3/text()').extract()[0].split()[0]
        polls = hxs.select('//*[@id="polling-data-full"]/table/tr[not(@class) or @class="isInRcpAvg"]')

        for poll in polls:
            polldata = poll.select('td/text() | td/a/text()')

            item = HousePollItem()
            item['state'] = state
            item['title'] = self._getStateAbbrev(state)+"-"+district
            item['service'] = polldata[ lookup['service'] ].extract()

            daterange = polldata[ lookup['date'] ].extract()
            item['start'], item['end'] = self._parsePollDates(daterange)

            sample = polldata[ lookup['sample'] ].extract()
            item['voters'], item['sample'] = self._parseSampleInfo(sample)

            item['dem']     = polldata[ lookup['dem'] ].extract()
            item['rep']     = polldata[ lookup['rep'] ].extract()
            try:
                item['ind'] = polldata[ lookup['ind'] ].extract()
            except:
                item['ind'] = 0
            item['candidates'] = hxs.select('//*[@id="polling-data-full"]/table/tbody/tr[1]/th[4]/text()').extract()
            item['candidates'] += hxs.select('//*[@id="polling-data-full"]/table/tbody/tr[1]/th[5]/text()').extract()
            items.append(item)

        return items

    def _getDataPositions(self, headers):
        """Determine the columns that each pollitem field's values are in.

        Args:
            headers
                An array of the text values for the Polling Data table headers.
                Ex: ["Poll", "Date", "Sample", "MoE", "Romney (R)", "Obama (D)", "Spread"]

        Returns
            A lookup dict that maps from pollitem fields to the related data's
            column position (an integer).

            Ex: {   "service": 0,
                    "date": 1,
                    "sample": 2,
                    "error": 3,
                    "dem": 5,
                    "rep": 4,
                }
        """
        lookup = {}

        i = 0
        for header in headers:
            attribute = parsePollData.getAttribute(header)
            if attribute is not None:
                lookup[attribute] = i

            i += 1

        return lookup

    def _getStateAbbrev(self, state):

        state_to_abbrev = {"VERMONT": "VT", "GEORGIA": "GA", "IOWA": "IA", "Armed Forces Pacific": "AP", "GUAM": "GU", "KANSAS": "KS", "FLORIDA": "FL", "AMERICAN SAMOA": "AS", "NORTH CAROLINA": "NC", "HAWAII": "HI", "NEW YORK": "NY", "CALIFORNIA": "CA", "ALABAMA": "AL", "IDAHO": "ID", "FEDERATED STATES OF MICRONESIA": "FM", "Armed Forces Americas": "AA", "DELAWARE": "DE", "ALASKA": "AK", "ILLINOIS": "IL", "Armed Forces Africa": "AE", "SOUTH DAKOTA": "SD", "CONNECTICUT": "CT", "MONTANA": "MT", "MASSACHUSETTS": "MA", "PUERTO RICO": "PR", "Armed Forces Canada": "AE", "NEW HAMPSHIRE": "NH", "MARYLAND": "MD", "NEW MEXICO": "NM", "MISSISSIPPI": "MS", "TENNESSEE": "TN", "PALAU": "PW", "COLORADO": "CO", "Armed Forces Middle East": "AE", "NEW JERSEY": "NJ", "UTAH": "UT", "MICHIGAN": "MI", "WEST VIRGINIA": "WV", "WASHINGTON": "WA", "MINNESOTA": "MN", "OREGON": "OR", "VIRGINIA": "VA", "VIRGIN ISLANDS": "VI", "MARSHALL ISLANDS": "MH", "WYOMING": "WY", "OHIO": "OH", "SOUTH CAROLINA": "SC", "INDIANA": "IN", "NEVADA": "NV", "LOUISIANA": "LA", "NORTHERN MARIANA ISLANDS": "MP", "NEBRASKA": "NE", "ARIZONA": "AZ", "WISCONSIN": "WI", "NORTH DAKOTA": "ND", "Armed Forces Europe": "AE", "PENNSYLVANIA": "PA", "OKLAHOMA": "OK", "KENTUCKY": "KY", "RHODE ISLAND": "RI", "DISTRICT OF COLUMBIA": "DC", "ARKANSAS": "AR", "MISSOURI": "MO", "TEXAS": "TX", "MAINE": "ME"}

        return state_to_abbrev[state.upper()]

    def _parsePollDates(self, dateText):
        """Find the start and end date of a poll.

        Break a date range string into the starting date and ending date.

        Args:
            dateText
                A string that describes the dates the poll was conducted
                during by providing a range from the poll's start date to
                its end date.  The year is ommitted.

                Ex: "10/1 - 10/3"
                    "5/3"

        Returns:
            An array with two entries:
                1: the poll's start date
                2: the poll's end date

            If there is only one date (eg. the poll was conducted during one
            day, or information is unknown) then that date is used as the
            end date and the start date is left as an empty string.

            The current year is appended to the end of the poll dates.  This is
            problematic since polls conducted in previous years are also listed.

            Ex: ["10/1/2012", "10/3/2012"]
                ["", "5/3/2012"]
        """
        # TODO: attempt to intelligently determine the year, instead of assuming
        #       that all polls occur in the current year?
        #       Are there any polls from previous years? YES
        daterange = dateText.split(' - ')
        start = ''
        end = ''

        # BugFix w/ If Statement and Array Resize
        #  - Preventative, based on the BugFix for _parseSampleInfo (see below)
        #  - Prevents errors when either the start or end dates is missing,
        #    so there is only one component in sampleInfo.
        if len(daterange) > 1:
            start = daterange[0] + '/2012'
            end = daterange[1] + '/2012'

        elif len(daterange) > 0:
            end = daterange[0] + '/2012'

        return start, end

    def _parseSampleInfo(self, sampleInfoText):
        """Find the sample size and sample type of a poll.

        Break a sample info string into its sample size and sample type
        components.

        Args:
            sampleInfoText
                A string that describes the population sampled by the poll.

                Ex: "595 LV"
                    "1337"
                    "RV"

        Returns:
            An array with two entries:
                1: the poll's sample size
                2: the poll's sample type (usually 'LV': likely voters, or 'RV':
                    registered voters)
            If there is only one component in the sample information (eg. the
                poll's sample size is unknown) then that component is used as
                the sample type and the sample size is left as an empty string.
                This is problematic because there are cases where sample size is
                the only component, thus the assumption is wrong.
            Ex: ["595", "LV"]
                ["", "1337"]
                ["", "RV"]
        """
        # TODO: attempt to intelligently guess which component is present if
        #       only one is.  This can be done by trying to read the component
        #       as an integer (which will work for sample size but not sample
        #       type).
        sampleInfo = sampleInfoText.split(' ')
        sampleSize = ''
        sampleType = ''

        # BugFix w/ If Statement
        #  - Prevents errors when either the sample size or the sample type
        #       (RV: registered voters, or LV: likely voters)
        #    is missing, thus there is only one component in sampleInfo which
        #    is assumed to be the sample type.
        if len(sampleInfo) > 1:
            sampleSize = sampleInfo[0]
            sampleType = sampleInfo[1]

        elif len(sampleInfo) > 0:
            # TODO: determine which component sampleInfo represents
            #       don't assume type, like currently does
            #       see above TODO
            sampleType = sampleInfo[0]

        return sampleSize, sampleType

    def processLinks(self, links):
        """
        Remove links to states with no polls.

        Args:
            links
                A list of links to follow, each of which represents a different
                state, which may or may not contain polling data.

        Returns
            A list of links to follow, each of which represents a different
            state that has polling data.
        """
        noPollLink = "http://www.realclearpolitics.com/epolls/2012/senate/2012_elections_electoral_college_map.html"

        for link in links:
            if link.url == noPollLink:
                links.remove(link)

        return links

    def processRequest(self, request):
        return request

    def _requests_to_follow(self, response):
        """
        Override the requests_to_follow function from CrawlSpider to allow link
        extraction from all files.  Specifically, javascript files need to work
        to get links from the RCP javascript file that generates the select box
        on http://www.realclearpolitics.com/epolls/latest_polls/president/.

        Args:
            response
                An html response that contains the presidential polling data for a state.

        Yields:
            Every link processed by each rule (so links x rules).
        """
        #if not isinstance(response, HtmlResponse):
        #    return
        seen = set()
        for n, rule in enumerate(self._rules):
            links = [l for l in rule.link_extractor.extract_links(response) if l not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            seen = seen.union(links)
            for link in links:
                r = Request(url=link.url, callback=self._response_downloaded)
                r.meta.update(rule=n, link_text=link.text)
                yield rule.process_request(r)
