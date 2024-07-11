import time
from property import Property
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc 
from bs4 import BeautifulSoup
from utils import is_convertible_to_int

class provider:

    def __init__(self,provider_name:str,base_url:str,property_type:str,driver:webdriver) -> None:
        
        self.provider_name = provider_name
        self.base_url = base_url
        self.property_type = property_type
        self.driver = driver

    def get_propertie_url(self,soup:BeautifulSoup)->list:

        list_properties_url = []
        properties = soup.find_all('div',class_='list-item-info')
        for propertie in properties:
            url = propertie.find('a')['href']
            list_properties_url.append(url)
        
        return list_properties_url

    def get_all_properties_in_page(self,driver:webdriver)->list:
        final_list = []
        for i in range(5):
            html_text = driver.page_source
            soup = BeautifulSoup(html_text)
            prop = self.get_propertie_url(soup)
            final_list = final_list + prop
            ActionChains(driver).key_down(Keys.PAGE_DOWN).key_up(Keys.PAGE_DOWN).perform()
            time.sleep(3)
        return list(set(final_list))
    
    def get_number_of_pages(self)->list:
        """
        return the max pages that exist in the page for Barcelona
        Args:
            driver(webdriver): selenium webdriver
        returns:
            int: integer of the max pages
        """
        max_page = 0
        html_text = self.driver.page_source
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
    
    def get_property_data(self,url:str)-> Property:

        self.driver.get(url)
        time.sleep(2)
        html_text = self.driver.page_source
        soup = BeautifulSoup(html_text,'html.parser')
        price = soup.find('div',class_='price').find('span',itemprop_='itemprop').get_text(strip=True)
        name = soup.find('div',class_='summary-left').find('h1').get_text(strip=True)
        location = name = soup.find('div',class_='summary-left').find('article',class_='location').find('a').get_text(strip=True)
        feature_conbtained = [ feature.find('strong').get_text(strip=True) for feature in soup.find('ul',class_="feature-container").find_all('li')]
        description = soup.find('p',id_='js-detail-description').get_text(strip=True)

    def main(self):

        #set chrome web driver
        
        
        #get web page
        self.driver.get("https://www.habitaclia.com/viviendas-barcelona.htm")

        #accept cookies
        time.sleep(3)
        cookies = self.driver.find_element(By.ID, "didomi-notice-agree-button")
        cookies.click()

        #get properties url
        time.sleep(0.5)
        properties_urls = self.get_all_properties_in_page()
        print(properties_urls)
        print(len(properties_urls))
        max_page = self.get_number_of_pages()
        self.get_property_data(properties_urls[0])
        
        #close web driver
        self.driver.close()