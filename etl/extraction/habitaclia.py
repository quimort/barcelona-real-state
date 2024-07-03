#import modules
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

def get_chrome_driver():
    driver = webdriver.Chrome()
    return driver

def main():

    #set chrome web driver
    driver = get_chrome_driver()
    #get web page
    driver.get("https://www.habitaclia.com/viviendas-barcelona.htm")

    #accept cookies
    time.sleep(2)
    cookies = driver.find_element(By.ID, "didomi-notice-agree-button")
    cookies.click()
    
    #close web driver
    driver.close()



if __name__ == "__main__":
    main()