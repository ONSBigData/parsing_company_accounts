# What's this?

The goal of the project in general is to be able to extract accounts
data from any company balance sheet from Companies House including those
submitted as an image/scan only.  

This repository exists so that others can join in on making this data
accessible.

Ultimately we want to be able to retrive the variables needed to fill
out the summary equation:

Assets = Liabilities + Shareholders' Equity


# Parsing digital company accounts data

The module xbrl_parser.py is for extracting data from xbrl company
account documents, both XBRLi and older XBRL formats.  It's currently
under development so it might be wise to play with it a bit and check
you're getting back what you expected!

The folder example_data_XBRL_iXBRL contains an assortment of recent
companies house accounts electronic records to play with as examples.

extract_XBRL.ipynb hosts example usage of the module in extracting
accounts.

The file example_extracted_XBRL_data.csv contains the results of 
applying these methods to all of the example digital accounts files,
flattened by a helper function into an SQL-friendly format.


The software, before "flattening", returns a python dict object:

```
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
				date: <from contextref attribute, will follow reference>}
				...
				...]}
```

# Parsing imaged company accounts data.

Experimenting with reading tables from CH PDF records.  Note, you can't
do much without Tesseract OCR version 4 (currently alpha) installed, and
all of the system commands that call external software in these notebooks
are set up for a linux machine.

The example PDF's, drawn randomly from Companies House a while back, are
in example_data_PDF directory.

03_Extract_PDF_data.ipynb uses Tesseract to "read" a pdf and convert it
to a table of words with locations and confidences in the translation.  
All the extraction code is now hidden in xbrl_image_parser.py.

The program gathers variables from the balance sheet entries in
the PDF by first narrowing to the pages likely to BE the balance sheet,
then using a sophisticated regex (from https://github.com/drkane) to 
get lines formatted with <some text> <number> <number> (simplified).
The reporting unit (eg; £, £000, $) is discovered by finding the most 
common currency unit followed or not by zeroes.

I'm assuming the dates of the records can be determined from metadata on
the Companies House API, but haven't actually checked.


# To be fixed;

"parsed" field should be False if no elements extracted from document. 
Currently it's False only if the document can't be opened in the first 
place.

(For reference; num of records with few numerical entries has proven to
be a good way of eyeballing data quality - there's too many edge cases 
in terms of content and formats so there's no definitive sign when 
things start to partially fail...)
