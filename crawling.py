import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from db import create_table, insert_menu
create_table()


driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)
driver.get("https://www.lotteeatz.com/brand/ria")

time.sleep(3)

tabs = driver.find_elements(By.CSS_SELECTOR, "#categoryList .tab-item")
# print(len(tabs)) ----> 6개

for i in range(len(tabs)):
    
    
    tabs = driver.find_elements(By.CSS_SELECTOR, "#categoryList .tab-item")
    tab_name = tabs[i].text.strip()
    
    print(f"\n=== {tab_name} ===")
    
    
    driver.execute_script("arguments[0].click();", tabs[i])
    time.sleep(2)
    
    items = driver.find_elements(By.CSS_SELECTOR, ".prod-tit")
    # print(len(items))  ---> 25 / 14 / 6 / 11 / 11
    
    for j in range(len(items)):
        
        main = driver.find_elements(By.CSS_SELECTOR, ".prod-item")
        
        try:
            badge = main[j].find_element(By.CSS_SELECTOR, ".thumb-box .text").text
        except NoSuchElementException:
            badge = ""    
        
        
        
        element = driver.find_elements(By.CSS_SELECTOR, ".btn-link")
        driver.execute_script("arguments[0].click();", element[j])
        
        img_url = driver.find_element(By.CSS_SELECTOR, ".thumb-img").value_of_css_property("background-image")
        img_url = img_url.replace('url("', '').replace('")', '')
        
        name = driver.find_element(By.CSS_SELECTOR, ".prod-tit").text
        price = driver.find_element(By.CSS_SELECTOR, ".val").text
        desc = driver.find_element(By.CSS_SELECTOR, ".btext").text
        
        
        detail_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-fold.detail-info")
        driver.execute_script("arguments[0].click();", detail_btn)
        
        time.sleep(1)
        
        rows = driver.find_elements(By.CSS_SELECTOR, ".tbl-row-info tbody tr")
        
        nutrition = {}
        
        for row in rows:
            
            key = row.find_element(By.CSS_SELECTOR, "th").text
            value = row.find_element(By.CSS_SELECTOR, "td").text
            nutrition[key] = value
            
        try:
            allergy = driver.find_element(By.XPATH, "//div[text()='알러지 정보']/following-sibling::p").text
        except NoSuchElementException:
            allergy = ""    
            
        try:   
            origin = driver.find_element(By.XPATH, "//div[text()='원산지 정보']/following-sibling::p").text
        except NoSuchElementException:
            origin = ""  

        
        # print(badge)  
        # print(name, price, desc)
        # print(img_url)
        # print(nutrition)
        # print(allergy)
        # print(origin)
        
        data = {
            "category": tab_name,
            "name": name,
            "badge": badge,
            "price": price,
            "description": desc,
            "img_url": img_url,
            "allergy": allergy,
            "origin": origin,
            "nutrition": nutrition
        }
        insert_menu(data)
        
        
        driver.back()
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".btn-link")))
        
        # time.sleep(2)
        
        
        

