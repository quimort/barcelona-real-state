#import modules
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

def get_chrome_driver()-> webdriver:
    driver = webdriver.Chrome()
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
    for i in range(15):
        html_text = driver.page_source
        soup = BeautifulSoup(html_text)
        prop = get_propertie_url(soup)
        final_list = final_list + prop
        ActionChains(driver).key_down(Keys.PAGE_DOWN).key_up(Keys.PAGE_DOWN).perform()
        time.sleep(1)
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
    soup = BeautifulSoup(html_text)
    all_nums = soup.find_all('ul',class_='f-right')
    nums = all_nums('a')
    print(all_nums) 

    return max_page
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

    
    #close web driver
    driver.close()



if __name__ == "__main__":
    main()