# What's this?

The goal of the project in general is to be able to extract accounts
data from any company balance sheet from Companies House including those
submitted as an image/scan only.  

This repository exists so that others can join in on making this data
accessible.

Ultimately we want to be able to retrive the variables needed to fill
out the summary equation:

Assets = Liabilities + Shareholders' Equity


# Parsing company accounts data (digital)

The module xbrl_parser.py is for extracting data from xbrl company
account documents, both XBRLi and older XBRL formats.  It's currently
under development so it might be wise to play with it a bit and check
you're getting back what you expected!

The folder example_data_XBRL_iXBRL contains an assortment of recent
companies house accounts electronic records to play with as examples.

extract_XBRL.ipynb hosts example usage of the module in extracting
accounts.

Schema of returned python dict object:

'''python
	{doc_name: <original file name>,
	doc_type: <file ending, html or xml>,
	doc_upload_date: <date of upload>,
	arc_name: <name of archive file from CH it was sourced from>,
	doc_parsed: <records True if the document was successfully parsed by BeautifulSoup>,
	doc_balancesheetdate: <date as extracted from filename>,
	doc_companieshouseregisterednumber: <CH company number as extracted from filename>
	doc_standard_type: <if found, name of accounting standard used in doc>,
	doc_standard_date: <if found, date of issue of the accounting standard used>,
	doc_standard_link: <if found, web link to official schema of the discovered accounting standard>,
	elements: [{name: <name found beginning with ix>,
				value: <result of get_text() applied to element, parsed to numeric if unit exists>,
				unit: <from unitref attribute, will follow reference and recognise USD, GBP and EUR>,
				date: <from contextref attribute, will follow reference>,
				occurence_index: <indexing of order of discovery of elements with this name>}
				...
				...]}
'''

# Parsing company accounts data (image)

Under construction
