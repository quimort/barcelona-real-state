#import modules
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from components.etl_components.property import Property
import undetected_chromedriver as uc 
from components.etl_components.utils import is_convertible_to_int



def get_chrome_driver():
    driver = driver = uc.Chrome() 
    return driver
def get_propertie_url(soup:BeautifulSoup)->list:

    list_properties_url = []
    properties = soup.find_all('div',class_='list-item-info')
    for propertie in properties:
        url = propertie.find('a')['href']
        list_properties_url.append(url)
    
    return list_properties_url

def get_all_properties_in_page(driver:webdriver)->list:
    final_list = []
    for i in range(5):
        html_text = driver.page_source
        soup = BeautifulSoup(html_text)
        prop = get_propertie_url(soup)
        final_list = final_list + prop
        ActionChains(driver).key_down(Keys.PAGE_DOWN).key_up(Keys.PAGE_DOWN).perform()
        time.sleep(3)
    return list(set(final_list))


def get_number_of_pages(driver:webdriver)->list:
    """
    return the max pages that exist in the page for Barcelona
    Args:
        driver(webdriver): selenium webdriver
    returns:
        int: integer of the max pages
    """
    max_page = 0
    html_text = driver.page_source
    list_numbers = []
    soup = BeautifulSoup(html_text,'html.parser')
    all_nums = soup.find_all('ul',class_='f-right')
    for num in all_nums:
        a_tags = num.find_all('a')
        for tags in a_tags:
            value = tags.get_text(strip=True)
            if is_convertible_to_int(value):
                list_numbers.append(tags.get_text(strip=True))
    print(list_numbers) 

    return max_page
def get_property_data(driver:webdriver,url:str)-> Property:

    driver.get(url)
    time.sleep(2)
    html_text = driver.page_source
    soup = BeautifulSoup(html_text,'html.parser')
    price = soup.find('div',class_='price').find('span',itemprop_='itemprop').get_text(strip=True)
    name = soup.find('div',class_='summary-left').find('h1').get_text(strip=True)
    location = name = soup.find('div',class_='summary-left').find('article',class_='location').find('a').get_text(strip=True)
    feature_conbtained = [ feature.find('strong').get_text(strip=True) for feature in soup.find('ul',class_="feature-container").find_all('li')]
    description = soup.find('p',id_='js-detail-description').get_text(strip=True)

def main():

    #set chrome web driver
    driver = get_chrome_driver()
    
    #get web page
    driver.get("https://www.habitaclia.com/viviendas-barcelona.htm")

    #accept cookies
    time.sleep(3)
    cookies = driver.find_element(By.ID, "didomi-notice-agree-button")
    cookies.click()

    #get properties url
    time.sleep(0.5)
    properties_urls = get_all_properties_in_page(driver)
    print(properties_urls)
    print(len(properties_urls))
    max_page = get_number_of_pages(driver)
    get_property_data(driver,properties_urls[0])
    
    #close web driver
    driver.close()



if __name__ == "__main__":
    main()