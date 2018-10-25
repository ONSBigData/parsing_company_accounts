"""

Martin Wood - Office for National Statistics
martin.wood@ons.gov.uk
23/07/2018

XBRL parser

Contains functions that scrape and clean an XBRL document's content
and variables, returning a dict ready for dumping into
MongoDB.

"""

import numpy as np
import pandas as pd
import os
import re

from datetime import datetime
from dateutil import parser
from bs4 import BeautifulSoup as BS  # Can parse xml or html docs


def clean_value(string):
	"""
	Take a value that's stored as a string,
	clean it and convert to numeric.
	
	If it's just a dash, it's taken to mean
	zero.
	"""
	if string.strip() == "-":
		return(0.0)
	
	try:
		return(float(string.strip().replace(",", "").replace(" ", "")))
	except:
		pass
	
	return(string)


def retrieve_from_context(soup, contextref):
	"""
	Used where an element of the document contained no data, only a
	reference to a context element.
	Finds the relevant context element and retrieves the relevant data.
	
	Returns a text string
	
	Keyword arguments:
	soup -- BeautifulSoup souped html/xml object
	contextref -- the id of the context element to be raided
	"""
	
	try:
		context = soup.find("xbrli:context", id=contextref)
		contents = context.find("xbrldi:explicitmember").get_text().split(":")[-1].strip()
		
	except:
		contents = ""
	
	return(contents)


def retrieve_accounting_standard(soup):
	"""
	Gets the account reporting standard in use in a document by hunting
	down the link to the schema reference sheet that always appears to
	be in the document, and extracting the format and standard date from
	the string of the url itself.
	WARNING - That means that there's a lot of implicity hardcoded info
	on the way these links are formated and referenced, within this
	function.  Might need changing someday.
	
	Returns a 3-tuple (standard, date, original url)
	
	Keyword arguments:
	soup -- BeautifulSoup souped html/xml object
	"""
	
	# Find the relevant link by its unique attribute
	link_obj = soup.find("link:schemaref")
	
	# If we didn't find anything it's an xml doc using a different
	# element name:
	if link_obj == None:
		link_obj = soup.find("schemaref")
	
	# extract the name of the .xsd schema file, which contains format
	# and date information
	text = link_obj['xlink:href'].split("/")[-1].split(".")[0]
	
	# Split the extracted text into format and date, return values
	return(text[:-10].strip("-"), text[-10:], link_obj['xlink:href'])
	
	
def retrieve_unit(soup, each):
	"""
	Gets the reporting unit by trying to chase a unitref to
	its source, alternatively uses element attribute unitref
	if it's not a reference to another element.
	
	Returns the unit
	
	Keyword arguments:
	soup -- BeautifulSoup souped html/xml object
	each -- element of BeautifulSoup souped object
	"""
	
	# If not, try to discover the unit string in the
	# soup object
	try:
		unit_str = soup.find(id=each['unitref']).get_text()
		
	except:
		# Or if not, in the attributes of the element
		try:
			unit_str = each.attrs['unitref']
			
		except:
			return("NA")
	
	# see if there's a detectable currency in there
	valid_currencies = ["USD",  "EUR", "GBP", "PURE"]
	
	for currency in valid_currencies:
		if currency in unit_str.upper():
			return(currency)
	
	return("other_"+unit_str)


def retrieve_date(soup, each):
	"""
	Gets the reporting date by trying to chase a contextref
	to its source and extract its period, alternatively uses
	element attribute contextref if it's not a reference
	to another element.

	Returns the date
	
	Keyword arguments:
	soup -- BeautifulSoup souped html/xml object
	each -- element of BeautifulSoup souped object
	"""
	
	# Try to find a date tag within the contextref element,
	# starting with the most specific tags, and starting with
	# those for ixbrl docs as it's the most common file.
	date_tag_list = ["xbrli:enddate",
					 "xbrli:instant",
					 "xbrli:period",
					 "enddate",
					 "instant",
					 "period"]
	
	for tag in date_tag_list:
		try:
			date_str = each['contextref']
			date_val = parser.parse(soup.find(id=each['contextref']).find(tag).get_text()).\
							  date().\
							  isoformat()
			return(date_val)
		except:
			pass
	
	try:
		date_str = each.attrs['contextref']
		date_val = parser.parse(each.attrs['contextref']).\
						  date().\
						  isoformat()
		return(date_val)
	except:
		pass
	
	return("NA")



def parse_element(soup, element):
	"""
	For a discovered XBRL tagged element, go through, retrieve its name
	and value and associated metadata.
	
	Keyword arguments:
	soup -- BeautifulSoup object of accounts document
	element -- soup object of discovered tagged element
	"""
	
	if "contextref" not in element.attrs:
		return({})
		
	element_dict = {}
	
	# Basic name and value
	try:
		# Method for XBRLi docs first
		element_dict['name'] = element.attrs['name'].lower().split(":")[-1]
	except:
		# Method for XBRL docs second
		element_dict['name'] = element.name.lower().split(":")[-1]
		
	element_dict['value'] = element.get_text()
	element_dict['unit'] = retrieve_unit(soup, element)
	element_dict['date'] = retrieve_date(soup, element)
			
	# If there's no value retrieved, try raiding the associated context data
	if element_dict['value'] == "":
		element_dict['value'] = retrieve_from_context(soup, element.attrs['contextref'])
	
	# If the value has a defined unit (eg a currency) convert to numeric	
	if element_dict['unit'] != "NA":
		element_dict['value'] = clean_value(element_dict['value'])
				
	return(element_dict)



def parse_elements(element_set, soup):
	"""
	For a set of discovered elements within a document, try to parse
	them.  Only keep valid results (test is whether field "name"
	exists).
	
	Keyword arguments:
	element_set -- BeautifulSoup iterable search result object
	soup -- BeautifulSoup object of accounts document
	"""
	elements = []
	for each in element_set:
		element_dict = parse_element(soup, each)
		if 'name' in element_dict:
			elements.append(element_dict)
	return(elements)



# REF UNDER DEVELOPMENT NOT YET IMPLEMENTED
def hunt_summary_values(doc,
						assets_list = ["netassetsliabilitiesincludingpensionasset",
                                       "netassetsliabilityexcludingpensionasset",
                                       "netassetsliabilities",
                                       "totalassetslesscurrentliabilities",
                                       "netcurrentassetsliabilities"],
						equity_list = ["shareholderfunds",
                                       "equity"],
                        interest_list = ["creditors",
                                         "debtors",
                                         'accountstypefullorabbreviated',
                                         'descriptionprincipalactivities',
                                         'accountingstandardsapplied',
                                         'entitytradingstatus',
                                         'statementthatcompanyentitledtoexemptionfromauditundersection477companiesact2006relatingtosmallcompanies']):
												
	"""
	Takes a document (dict) after extraction, and tries to extract
	summary variables relating to the financial state of the enterprise.
	Returns dict.
	
	The default values are included to save effort, and are correct at
	the time of construction of these functions (11/10/2018).
	
	Keyword arguments:
	doc -- an extracted document dict, with "elements" entry as created
	       by the 'scrape_clean_elements' functions.
	assets_list -- variable names that are commonly used to mark
	               net assets/liabilities, in prioritised order.
	funds_list -- variable names that are commonly used to mark
	              shareholder's equity, in prioritised order.
	interest_list -- names of other variables that might be of interest
	                 in aggregating data.  Eg;  Capital Reserves.
	"""
	
	results = {}
	
	# Convert elements to pandas df
	df = pd.DataFrame(doc['elements'])
	df = df[df['date'] == doc['doc_balancesheetdate']]
	
	# Find the net asset/liability variable
	for each in assets_list:
		try:
			results['net_assets_liabilities'] = df[df['name'] == each].iloc[0]['value']
			results['balance_sheet_unit'] = df[df['name'] == each].iloc[0]['unit']
			break
		
		except:
			pass
	
	# Find the shareholder's equity/funds variable
	for each in equity_list:
		try:
			results['shareholder_equity'] = df[df['name'] == each].iloc[0]['value']
			break
		
		except:
			pass
	
	# Find all the other variables  of interest should they exist
	for each in interest_list:
		try:
			results[each] = df[df['name'] == each].iloc[0]['value']
		
		except:
			pass
	
	# Send the variables back to be appended
	return(results)
	
	
def scrape_elements(soup, filepath):
	"""
	Parses an XBRL (xml) company accounts file
	for all labelled content and extracts the
	content (and metadata, eg; unitref) of each
	element found to a dictionary 
	
	params: filepath (str)
	output: list of dicts
	"""
	
	# Try multiple methods of retrieving data, I think only the first is
	# now needed though.  The rest will be removed after testing this
	# but should not affect execution speed.
	try:
		element_set = soup.find_all()
		elements = parse_elements(element_set, soup)
		if len(elements) <= 5:
			raise Exception("Elements should be gte 5, was {}".format(len(elements)))
		return(elements)
	except:
		pass
		
	try:
		xbrl = soup.find_all("xbrl")
		element_set = xbrl.find_all()
		elements = parse_elements(element_set, soup)
		if len(elements) <= 5:
			raise Exception("Elements should be gte 5, was {}".format(len(elements)))
		return(elements)
	except:
		pass
	
	try:
		xbrl = soup.find_all()
		element_set = xbrl.find_all()
		elements = parse_elements(element_set, soup)
		if len(elements) <= 5:
			raise Exception("Elements should be gte 5, was {}".format(len(elements)))
		return(elements)
	except:
		pass
	
	try:
		xbrl = soup.find_all("xbrl")
		element_set = xbrl[0].find_all()
		elements = parse_elements(element_set, soup)
		if len(elements) <= 5:
			raise Exception("Elements should be gte 5, was {}".format(len(elements)))
		return(elements)
	except:
		pass
	
	try:
		xbrl = soup.find_all()
		element_set = xbrl[0].find_all()
		elements = parse_elements(element_set, soup)
		if len(elements) <= 5:
			raise Exception("Elements should be gte 5, was {}".format(len(elements)))
		return(elements)
	except:
		pass
		
	return(0)


def process_account(filepath):
	"""
	Scrape all of the relevant information from
	an iXBRL (html) file, upload the elements
	and some metadata to a mongodb.
	
	Named arguments:
	filepath -- complete filepath (string) from drive root
	"""
	doc = {}
	
	# Some metadata, doc name, upload date/time, archive file it came from
	doc['doc_name'] = filepath.split("/")[-1]
	doc['doc_type'] = filepath.split(".")[-1].lower()
	doc['doc_upload_date'] = str(datetime.now())
	doc['arc_name'] = filepath.split("/")[-2]
	doc['parsed'] = True
	
	# Complicated ones
	sheet_date = filepath.split("/")[-1].split(".")[0].split("_")[-1]
	doc['doc_balancesheetdate'] = datetime.strptime(sheet_date, "%Y%m%d").date().isoformat()
	
	doc['doc_companieshouseregisterednumber'] = filepath.split("/")[-1].split(".")[0].split("_")[-2]
	
	print(filepath)
	
	try:
		soup = BS(open(filepath, "rb"), "html.parser")
	except:
		print("Failed to open: " + filepath)
		return(1)
	
	# Get metadata about the accounting standard used
	try:
		doc['doc_standard_type'], doc['doc_standard_date'], doc['doc_standard_link'] = retrieve_accounting_standard(soup)
	except:
		doc['doc_standard_type'], doc['doc_standard_date'], doc['doc_standard_link'] = (0, 0, 0)
	
	# Fetch all the marked elements of the document
	try:
		doc['elements'] = scrape_elements(soup, filepath)
	except Exception as e:
		doc['parsed'] = False
		doc['Error'] = e
	
	try:
		return(doc)
	except Exception as e:
		return(e)
