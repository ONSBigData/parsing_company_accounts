"""

Martin Wood - Office for National Statistics
martin.wood@ons.gov.uk
15/11/2018

XBRL image parser

Contains functions to take the data created by passing a company's
balance sheet through Google's Tesseract OCR software (v4), and extract
useful financial variables from it.

Will eventually contain system calls for use on Linux to call the OCR
process.

"""

import os
import re

import numpy as np
import pandas as pd

from datetime import datetime
from dateutil import parser


def make_measurements(data):
	"""
	Takes the tabulated OCR output data (pandas DF) and interprets to
	create more variables, geometric information on where elements are
	on the page.
	"""
	
	# Creating some new useful variables
	data['centre_x'] = data['left'] + ( data['width'] / 2. )
	data['centre_y'] = data['top'] + ( data['height'] / 2. )
	data['right'] = data['left'] + data['width']
	data['bottom'] = data['top'] + data['height']
	data['area'] = data['height'] * data['width']
	
	# Shifted values for calcuating word spacing
	# This can be useful for identifying sparsely
	data['space_from_left'] = np.where((data['word_num'] == 0) | (data['word_num'] == 1),
									   np.nan,
									   data['left'] - data['right'].shift())
	
	# Data already ordered by page, block, paragraph, line and word number.
	# Want to create unique line identifier.
	line_lookup = data[['csv_num', 'page_num', 'block_num', 'par_num', 'line_num']].\
		groupby(['csv_num', 'page_num', 'block_num', 'par_num', 'line_num']).\
		size().\
		reset_index().\
		rename(columns={0:'line_word_count'})
	
	# Stick the line index back on to the data
	line_lookup['line_index'] = line_lookup.index.values
	line_data = data.merge(line_lookup, on=['csv_num', 'page_num', 'block_num', 'par_num', 'line_num'], how="left")
	
	# Calculate some whole_document spacing statistics
	line_data['doc_spacing_mean'] = line_data['space_from_left'].sum() / line_data['space_from_left'].count()
	line_data['doc_spacing_median'] = line_data['space_from_left'].median()
	line_data['doc_spacing_sd'] = np.sqrt( np.sum( (line_data['space_from_left'] - line_data['doc_spacing_mean']) ** 2. ) / (line_data['space_from_left'].count() - 1.) )

	return( line_data )


def convert_to_numeric(series):
	"""
	Converts a pandas series object (of strings) to numeric if possible.
	If not possible, will return numpy.nan.
	"""
	q_func = lambda x: str(x).replace(",", "").strip("(").strip(")")
	
	numeric_series = pd.to_numeric(series.apply(q_func), errors="coerce")             # If errors, force process to continue, invalid element returned as numpy.nan
	
	return(numeric_series)


def find_pages(dat, keystring):
	"""
	Filter to pages (using csv_num) that have a mention of a specific
	phrase or word on any line.  This is meant to reduce the risk of the
	software consulting the wrong table.
	"""
	
	dat_agg = agg_level(dat, 4)
	
	dat_agg = dat_agg[dat_agg['text'].apply(lambda x: keystring in x.lower())]
	
	csv_numbers = dat_agg['csv_num'].unique()
	
	return(dat[dat['csv_num'].apply(lambda x: x in csv_numbers)])


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
	
	print(units)
	
	# Return most common units
	return( (units.loc[0, "text"], units.loc[0, "count"]) )


def determine_years_count(subset, limits=[2000, 2050]):
	"""
	Simplistic method that finds the years for a document through
	counting all year-format strings, finding the two most common and
	seeing if the difference is only one as an arbitrary QA.
	"""

	# Search in the value range of interest
	subset['keyword_found'] = (subset['numerical'] >= limits[0]) & (subset['numerical'] <= limits[1])
	
	subset = subset[subset['keyword_found']==True]
	subset['count'] = 1
	
	candidates = subset[["numerical", "count"]].\
						groupby("numerical").\
						count().\
						reset_index().\
						sort_values("count", ascending=False)['numerical'][0:2].values
	
	if (candidates[0] - candidates[1]) == 1:
		return(candidates)
	
	else:
		return(0)
	

def aggregate_sentences_over_lines(dat):
	"""
	Aggregates all text marked as being in the same line.  Then finds
	text that was split over multiple lines by checking if the line
	starts with a capital letter or not.
	"""
	
	dat_group = dat.groupby(["csv_num", "block_num",  "par_num", "line_num"])
	
	# Create aggregate line text
	line_text = dat_group['text'].apply(lambda x: " ".join([str(e) for e in list(x)]).strip("nan "))
	line_text = line_text.reset_index()
	
	# Create line bounding boxes for page
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
	
	# Drop any entries where the text field contains a number
	results = results[np.where(results['text'].apply(lambda x: re.search(".*[0-9].*", x)), False, True)]
	
	# Format the text field
	results['text'] = results['text'].apply(lambda x: re.sub("[^a-z]+", "", x.lower()))
	
	# Drop any now-empty
	results = results[results['text'].apply(lambda x: len(x.strip()) > 0)]
	
	return(results.drop("continued_line", axis=1))


########################################################################

###  Everything beyond here's legacy code from the old approach ###

########################################################################

def agg_level(dat, level=4):
	"""
	Text data read in by Tesseract OCR is grouped by level (highest
	number is most granular and represents words, lowest number is least
	granular and represents blocks of content).
	
	This function takes the data and aggregates, or rather concatenates,
	text to a specified level.
	
	Facilitates search for more complex strings that may be split across
	lines, paragraphs or blocks and so on.
	
	Default level indicates lines
	"""
	
	dat = dat[dat['level']>=level][['csv_num', 'block_num', 'par_num', 'line_num', 'text']]
	
	# Not certain the "nan" value stripper below will work as expected
	mat = dat.groupby(["csv_num", "block_num", "par_num", "line_num"])['text'].\
			   apply(lambda x: " ".join([str(e) for e in list(x)]).strip("nan ")).\
			   reset_index()
	
	return(mat)


def agg_two_lines(dat):
	"""
	For each table entry, create a field that has the aggregated text of
	all text from the line the entry is on, plus all text from the next
	line the entry is on.  This is in order to create one field within
	which to search for variable names that, if long, may be split over
	two lines.
	
	This function is assuming the data is ordered, as it is if you take 
	it straight from TesseractOCR.
	"""

	# Create aggregated table of line text + indexing columns only
	dat_agg = agg_level(dat)
	
	# Append aggregated text column (each line + its next line)
	dat_agg['text_agg'] = dat_agg['text'] + " " + dat_agg['text'].shift(-1)
	
	# drop old text column
	dat_agg = dat_agg.drop('text', axis=1)
	
	# Merge 'text_agg' column onto original dataset, one to many
	dat_merged = dat.merge(dat_agg,
                on=["csv_num", "block_num", "par_num", "line_num"],
                how="left")
	
	return(dat_merged)
	#return(dat_merged[(dat_merged['word_num'] == 0) &
	#				  (dat_merged['line_num'] > 0)])


def extract_stat(dat, keyword):
	"""
	Implements a process for finding key numbers based upon position on
	page - finds first the element name of interest ('keyword'), all
	occurences.  Gets any numbers horizontally aligned with the keyword
	and then returns the right-most two.
	"""
	
	# Find examples of the keyword of interest
	dat['keyword_found'] = dat['text']==keyword
	
	elements = pd.DataFrame()
	
	# For keyword, hunt down all numerical values roughly horizontally
	# aligned with it
	for index, row in dat[dat['keyword_found']==True].iterrows():
		
		selection = dat[(dat['top'] < row['bottom']) &                  # Subset to elements roughly in line with keyword
						(dat['bottom'] > row['top']) &                  # Remembering w. vertical position 0 is at top
						(dat['csv_num'] == row['csv_num']) &            # Make sure we're (literally) on the same page
						(dat['left'] > row['left'])]                    # Make sure the numbers are to the right of the row label
						#(pd.isna(dat['numerical'])==False)]
						   
		# Assign an index to the search results matching the line index 
		# of the original keyword.  Take the two right-most numbers.
		selection['keyword_index'] = index
		selection = selection.sort_values("left", ascending=False).\
							  iloc[0:2,].\
							  sort_values("left", ascending=True)
		
		print(selection['text'])
		elements = elements.append(selection)
	
	elements = elements.iloc[0:2,]
	
	# Take only the first positive identified
	return(tuple(elements['text']),
		   tuple(elements['numerical']),
		   tuple(elements['conf']))

# Find a statistic in the discovered tables...UPGRADED!
def extract_stat_linesearch(dat, keyphrase):
	"""
	Implements a process for finding key numbers based upon position on
	page - finds first the element name of interest ('keyphrase'), all
	occurences even if spread over two lines.  Gets any numbers
	horizontally aligned with the keyphrase and then returns the 
	right-most two.
	"""
	
	dat_agg = agg_two_lines(dat)
	
	# Find examples of the keyword of interest
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: keyphrase in str(x))]
	
	# Filter to those which begin with the same first four characters
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: x.startswith(keyphrase[:4]))]
	
	# Take first result, hunt down all numbers aligned with it
	row = dat_agg.iloc[0]
	
	selection = dat[(dat['top'] < row['bottom']) &                              # Subset to elements roughly in line with keyword
					(dat['bottom'] > row['top']) &                              # Remembering w. vertical position 0 is at top
					(dat['csv_num'] == row['csv_num']) &                        # Make sure we're (literally) on the same page
					(dat['left'] > row['left']) &                               # Make sure the numbers are to the right of the row label
					(pd.isna(dat['numerical'])==False)]			   

	# Get the two right-most results
	selection = selection.sort_values("left", ascending=False).\
						  iloc[0:2,].\
						  sort_values("left", ascending=True)
	
	# Record some metadata about the match found					  
	selection['text_matched'] = row['text_agg']
	selection['text_original'] = row['text']
	
	return(tuple(selection['numerical']),
		   tuple(selection['conf']))


def extract_parallel_numbers(dat, row):
	"""
	Finds and returns all numerical entries that are parallel on a page
	to the text in 'row'.  Row should be a pandas Series object comprised
	of a single extracted row from the DF created from the document.
	"""
	
	selection = dat[(dat['top'] < int(row['bottom'])) &                              # Subset to elements roughly in line with keyword
					(dat['bottom'] > int(row['top'])) &                              # Remembering w. vertical position 0 is at top
					(dat['csv_num'] == int(row['csv_num'])) &                        # Make sure we're (literally) on the same page
					(dat['left'] > int(row['left'])) &                               # Make sure the numbers are to the right of the row label
					(pd.isna(dat['numerical'])==False)]	
	
	return(selection)

def find_element_location(dat, keyphrase):
	"""
	Finds a row corresponding to the first word of a phrase of interest.
	"""
	
	# Create an aggregated text field of the text from the whole line
	# and the next line down
	dat_agg = agg_two_lines(dat)
	
	# Find examples of the keyword of interest
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: keyphrase in str(x))]
	
	# Filter to those which begin with the same first four characters
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: x.startswith(keyphrase[:4]))]
	
	# Return one representative row, corresponding to the first word in
	# the line/phrase.  Allows for multiple matches.
	return(dat_agg[dat_agg['word_num'] == 1])	
	

def extract_stat_linesearch2(dat, keyphrase):
	"""
	Implements a process for finding key numbers based upon position on
	page - finds first the element name of interest ('keyphrase'), all
	occurences even if spread over two lines.  Gets any numbers
	horizontally aligned with the keyphrase and then returns the 
	right-most two.
	"""
	
	dat_agg = agg_two_lines(dat)
	
	# Find examples of the keyword of interest
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: keyphrase in str(x))]
	
	# Filter to those which begin with the same first four characters
	dat_agg = dat_agg[dat_agg['text_agg'].apply(lambda x: x.startswith(keyphrase[:4]))]
	
	print(dat_agg.iloc[0:2][['text', 'text_agg']])
	
	results = pd.DataFrame()
	
	# Take first result, hunt down all numbers aligned with it
	for index, row in dat_agg.iloc[0:2].iterrows():
	
		selection = extract_parallel_numbers(dat, row)		   

		# Record some metadata about the match found					  
		selection['text_matched'] = row['text_agg']
		selection['text_original'] = row['text']
		
		results = results.append(selection)
	
	return(results)
	

def find_statistics(dat, keystring):
	"""
	Try to get a statistic based upon a key phrase or word.
	First tries to get it by searching the exact keyword/s,
	then if that returns nothing it tries a more complex method
	over multiple (2) lines.
	"""
	
	try:
		stats = extract_stat(dat, keystring)
		if len(stats) > 0:
			return(stats)
	
	except:
		
		try:
			stats = extract_stat_complex(dat, keystring)
			if len(stats) > 0:
				return(stats)
		
		except Exception as e:
			print("Couldn't find a stat: " + keystring + ", exception: " + str(e))
	
	return(0)






