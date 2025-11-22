"""Тестовий скрипт для перевірки Flet"""
import flet as ft

def main(page: ft.Page):
    page.title = "Test Flet"
    page.add(ft.Text("Flet працює!"))

if __name__ == "__main__":
    ft.app(target=main)


