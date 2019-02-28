"""

Martin Wood - Office for National Statistics
martin.wood@ons.gov.uk
15/11/2018

XBRL image parser

Contains functions to take the data created by passing a company's PDF
balance sheet through Google's Tesseract OCR software (v4), and extract
useful financial variables from it.

These processes are VERY reliant on the format of the output of the
TesseractOCR software.

Will eventually contain system calls for use on Linux to call the OCR
process.

"""

# General
import sys
import os
import re

import numpy as np
import pandas as pd

from datetime import datetime
from dateutil import parser

# For image processing
import pytesseract
import cv2
import PyPDF2
import io

from io import StringIO
from wand.image import Image
from PIL import Image as im
import codecs

# Disable an annoying (and superfluous) warning
pd.options.mode.chained_assignment = None

def pdf_to_png(filepath):
	"""
	Convert PDF to PNG image using Cairo reader/converter in linux CM
	"""
	destination_filepath = filepath.replace(".pdf", "")
	
	os.system("pdftocairo -r 300 -png " + filepath + " " + destination_filepath)
	
	return(destination_filepath)
	

def pre_process(png_filepath):
	"""
	Image pre-processing entails finding all of the png image files and
	applying a number of cleaning steps to them.
	"""
	#find all of the converted pages
	filename = png_filepath.split("/")[-1]
	filepath = png_filepath.replace(filename, "")
	
	png_files = [pngname for pngname in os.listdir(filepath) if (filename in pngname) & (".png" in pngname)]
	
	for pngname in png_files:
		
		# Read in as greyscale
		concatenated = cv2.imread(filepath + "/" + pngname, 0)
	
		# Threshold image to black/white (threshold = 127 I presume)
		num, grey_composite = cv2.threshold(concatenated, 127, 255, cv2.THRESH_BINARY)
		
		# inverting the image for morphological operations
		inverted_composite = 255-grey_composite
	
		# Perform closing, dilation followed by erosion
		kernel = np.ones((2,2), np.uint8) 
		closed_composite = cv2.morphologyEx(inverted_composite, cv2.MORPH_CLOSE, kernel)
		
		# Undo inversion
		closed_composite = 255-closed_composite
		
		# Write over original with processed version
		cv2.imwrite(filepath + pngname, closed_composite)
		
	return([filepath + pngname for pngname in png_files])


def ocr_pdf(filepath):
	"""
	Given a pdf file, fixes it, pre-processes it and then applies OCR to
	it.
	"""
	
	# Process single PDF to multiple png files of individual pages
	print("Converting PDF image to multiple png files")
	print(filepath)
	png_filepath = pdf_to_png(filepath)
	
	# preprocess all images and pass out list of individual filepaths
	print("Performing pre-processing on all png images")
	png_filepaths = pre_process(png_filepath)
	
	# Apply OCR to every page
	doc_df = pd.DataFrame()
	csv_num = 1
	
	for pngpath in png_filepaths:
		try:
			page_df = pd.read_csv(StringIO(pytesseract.image_to_data(im.open(pngpath))),
									sep=' |\t',
									error_bad_lines=False,
									engine='python')
		
			page_df['csv_num'] = csv_num
		
			doc_df = doc_df.append(page_df)
			csv_num += 1
			
		except:
			print("Failed on " + pngpath)
			csv_num += 1
	
	# Cleanup - delete all of the generated csv and png files...
	for filepath in png_filepaths:
		os.system("rm " + filepath)
		
	return(doc_df)
	

def make_measurements(data):
	"""
	Takes the tabulated OCR output data (pandas DF) and interprets to
	create more variables, geometric information on where elements are
	on the page.
	"""
	
	data['centre_x'] = data['left'] + ( data['width'] / 2. )
	data['centre_y'] = data['top'] + ( data['height'] / 2. )
	data['right'] = data['left'] + data['width']
	data['bottom'] = data['top'] + data['height']
	data['area'] = data['height'] * data['width']
	
	return( data )
	
	
def convert_to_numeric(series):
	"""
	Converts a pandas series object (of strings) to numeric if possible.
	If not possible, will return numpy.nan.
	"""
	q_func = lambda x: str(x).replace(",", "").strip("(").strip(")")
	
	return( pd.to_numeric(series.apply(q_func), errors="coerce") ) # If errors, force process to continue, invalid element returned as numpy.nan


def determine_units_count(subset):
	"""
	Simplistic method that finds the units of numbers through counting
	all strings that start with given units, and returning the most common.
	"""
	
	units_regex = "[£$]|million|thousand|£m|£k|$m|$k"
	
	# Search for matches
	subset['keyword_found'] = subset['text'].apply(lambda x: bool(re.match(units_regex, str(x))))
	
	subset = subset[subset['keyword_found']==True]
	subset['count'] = 1
	
	# List and sort units by count
	units=subset[["text", "count"]].\
		  groupby("text").\
		  count().\
		  sort_values("count", ascending=False).\
		  reset_index()
	
	# Return most common units
	return( (units.loc[0, "text"], units.loc[0, "count"]) )


def determine_years_count(subset, limits=[2000, 2050]):
	"""
	Simplistic method that finds the years for a document through
	counting all year-format strings, finding the most common.
	"""

	# Search in the value range of interest
	subset['keyword_found'] = (subset['numerical'] >= limits[0]) & (subset['numerical'] <= limits[1])
	
	subset = subset[subset['keyword_found']==True]
	subset['count'] = 1
	
	candidates = subset[["numerical", "count"]].\
						groupby("numerical").\
						count().\
						reset_index().\
						sort_values("count", ascending=False)['numerical'].values
	
	return(np.array([candidates[0], candidates[0] - 1]))
	

def aggregate_sentences_over_lines(dat):
	"""
	Aggregates all text marked as being in the same line.  Then finds
	text that was split over multiple lines by checking if the line
	starts with a capital letter or not.
	"""
	
	# Drop empty entries with no text
	dat = dat[dat['text'].isnull() == False]
	
	dat_group = dat[dat['numerical'].isnull()]
	
	dat_group = dat_group.groupby(["csv_num", "block_num",  "par_num", "line_num"])
	
	# Create aggregate line text
	line_text = dat_group['text'].apply(lambda x: " ".join([str(e) for e in list(x)]).strip("nan "))
	line_text = line_text.reset_index()
	
	# Create line bounding boxes for line groups
	line_text['top'] = dat_group['top'].agg('min').reset_index()['top']
	line_text['bottom'] = dat_group['bottom'].agg('max').reset_index()['bottom']
	line_text['left'] = dat_group['left'].agg('min').reset_index()['left']
	line_text['right'] = dat_group['right'].agg('max').reset_index()['right']
	
	# Identify lines that start with a lowercase letter.  Misses continued
	# lines that start with a number.  If I cared, I would check if the
	# previous line ended with a period.
	line_text['continued_line'] = line_text['text'].apply(lambda x: np.where(re.search("^[a-z].*", x.strip()), True, False))
	
	# Find the sentences that start with a lowercase letter
	results = pd.DataFrame()

	row_of_interest = line_text.iloc[0,:]
	
	# Iterate through and aggregate any lines that are continued
	for index, row in line_text.iterrows():
	
		if (row['continued_line']==True) & (index != 0) :
		
			# If continued line, update values
			row_of_interest['text'] = row_of_interest['text'] + " " + row['text']
			row_of_interest['bottom'] = row['bottom']
			row_of_interest['left'] = min([row_of_interest['left'], row['left']])
			row_of_interest['right'] = max([row_of_interest['right'], row['right']])
	
		else:
			results = results.append(row_of_interest)
			row_of_interest = row
	
	# Format the text field, stripping any accidentally included numbers
	results['text'] = results['text'].apply(lambda x: re.sub("[^a-z]+", "", x.lower()))
	
	# Drop any now-empty
	results = results[results['text'].apply(lambda x: len(x.strip()) > 0)]
	
	return(results.drop("continued_line", axis=1))


def find_balance_sheet_pages(data):
	"""
	Through holistic steps, identify pages likely to contain the balance
	sheet.  This includes finding sentences starting
	[abbreviated]*balancesheet, and excluding pages containing
	'notestothefinancialstatements' and 'statementof'.
	"""
	
	# Create a table with aggregated sentences over lines
	agg_text = aggregate_sentences_over_lines(data)
	
	# Get a list of pages likely to be balance sheets
	BS_page_list = pd.unique(agg_text[agg_text['text'].apply(lambda x: np.where( re.search( "^[abbreviated]*balancesheet", x ), True, False))]['csv_num'])
	
	pos_page_list = pd.unique(agg_text[agg_text['text'].apply(lambda x: np.where( re.search( "^statementoffin", x ), True, False))]['csv_num'])
	
	# Filter out any page with the words "notes to the financial statements"
	notes_page_list = pd.unique(agg_text[agg_text['text'].apply(lambda x: "notestothefinancialstatements" in x)]['csv_num'])
	
	# Filter out any page with the words "Statement of changes in equity"
	statement_page_list = pd.unique(agg_text[agg_text['text'].apply(lambda x: "statementof" in x)]['csv_num'])
	
	return( [x for x in BS_page_list if x not in list(notes_page_list) + list(statement_page_list)] + list(pos_page_list) )
	

# Lifted this almost directly from David Kane's work
def detect_lines(page_df, x_tolerance=0, height_tolerance=20.0):
	"""
	Detect lines in the csv of a page, returned by Tesseract
	"""
	words_df = page_df[page_df['word_num'] > 0]
	page_stats = page_df.iloc[0, :]
	
	row_ranges = []
	this_range = []
	
	# Clean up the words list, removing blank entries and null values that can arise
	words_df = words_df[words_df['text'].apply(lambda x: str(x).strip() != "")]                   # blank strings
	words_df = words_df[words_df['text'].apply(lambda x: str(x).strip("|") != "")]                # Vertical separators (arise when edges of bounded tables detected)
	words_df = words_df[words_df['text'].isnull() ==False]                                        # Null values (I don't know how they can even exist!)
	words_df = words_df[words_df['height'] < page_stats['height'] / height_tolerance]             # Any word with height greater than 1/20th fraction of page height
	
	# Iterate through every vertical pixel position, top (0) to bottom (height)
	for i in range(page_stats['height']): 
		result = (( words_df['bottom'] >= i ) & ( words_df['top'] <= i )).sum() > 0
		
		# Append vertical pixels aligned with words to this_range
		if result:
			this_range.append(i)
		
		# If we've passed out of an "occupied" range, append the resulting range to a list to store
		else:
			if this_range:
				row_ranges.append(this_range)
			this_range = []
			
	# Create bounding boxes for convenience
	return[{"left":0, "right":page_stats['width'], "top":min(r), "bottom":max(r)} for r in row_ranges]
	

def extract_lines(page_df, lines):
	
	# Look, dark magic!
	finance_regex = r'(.*)\s+(\(?\-?[\,0-9]+\)?)\s+(\(?\-?[\,0-9]+\)?)$'
	
	words_df = page_df[page_df['word_num'] > 0]
	
	raw_lines = []
	results = pd.DataFrame()
	for line in lines:
		
		# Retrieve all text in line
		inline = (words_df['bottom'] <= line['bottom']) & (words_df['top'] >= line['top'])
		line_text = " ".join([str(x) for x in words_df[inline]['text']] )
		
		# Remove any character that isn't a letter, a number or a period
		line_text = re.sub(r'[^a-zA-Z0-9. +]', "", line_text)
		raw_lines.append(line_text)
		
		# Perform an incredibly complex regex search to extract right-most two numbers and the label
		result = re.match(finance_regex, line_text)
		
		# Retrieve the NN's confidence in its translations
		confidences = list(words_df[inline]['conf'])
		
		if result:
			
			try:
				# Check if label is a continuation, if so, append text from last line
				if re.match(r'^[a-z]',re.sub("[0-9]", "", result.groups()[0]).strip()[0]):
					label = raw_lines[-2] + " " + re.sub("[0-9]", "", result.groups()[0]).strip()
				else:
					label = re.sub("[0-9]", "", result.groups()[0]).strip()
			
				results = results.append({"label":label,
										"value":result.groups()[1],
										"currYr":True,
										"source":line_text,
										"conf":confidences[-1]},
										ignore_index=True)
			
				results = results.append({"label":label,
										"value":result.groups()[2],
										"currYr":False,
										"source":line_text,
										"conf":confidences[-2]},
										ignore_index=True)
			except:
				print("Failed to process line: " + line_text)
	
	return(results)


def process_PDF(filepath):
	"""
	Call all the functions, get all the data...
	"""
	data = ocr_pdf(filepath)
	
	# Do some geometry (eg; calculate specific coords of "bottom")
	data = make_measurements(data)
	
	# Create numerical variables from text where possible
	data['numerical'] = convert_to_numeric(data['text'])
	
	# Find the balance sheet pages
	csv_numbers = find_balance_sheet_pages(data)
	
	results = pd.DataFrame()
	
	# Iterate through balance sheet pages, retrieve everything
	for csv_number in csv_numbers:
		page_df = data[data['csv_num'] == csv_number]
		
		# Determine where the lines are
		detected_lines = detect_lines(page_df)
		
		# Get all detectable balance sheet stats
		results = results.append( extract_lines(page_df, detected_lines) )
	
	years = determine_years_count(data)
	units = determine_units_count(data)
	
	results['year'] = np.where( results['currYr']==True, years.max(), years.min() )
	results['unit'] = units[0]
	
	return( results )
	


