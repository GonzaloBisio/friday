"""Integraciones externas de FRIDAY (Spotify, Sheets, etc.).

Cada integración es un módulo con funciones simples, registradas como acciones
en el ActionRegistry con su nivel de riesgo. Así heredan el gate de permisos y
el LLM las invoca por el mismo puente que las acciones de PC.
"""
