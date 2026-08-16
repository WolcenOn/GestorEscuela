# GestorEscuela

Núcleo experimental de una plataforma inteligente de organización, ausencias, sustituciones y resiliencia escolar.

## Fase actual

La primera fase valida el producto matemáticamente antes de construir API, frontend o integraciones. Incluye:

- modelo de dominio mínimo y tipado;
- dataset ficticio de 6 grupos, 12 docentes y 6 franjas;
- optimización global de ausencias mediante OR-Tools CP-SAT;
- restricciones duras de disponibilidad, compatibilidad y no solapamiento;
- penalizaciones por desplazar actividades, historial de sustituciones y uso de perfiles de emergencia;
- protección explícita de PT/AL de prioridad alta;
- soluciones parciales cuando no existe cobertura completa;
- explicaciones en lenguaje de dominio;
- tests y simulación reproducible.

## Ejecutar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python simulate.py
pytest
```

## Estructura

```text
src/gestor_escuela/
├── domain/
│   └── models.py
├── solver/
│   ├── optimizer.py
│   └── explanations.py
└── simulation/
    └── dataset.py

tests/
docs/adr/
simulate.py
```

## Alcance deliberadamente excluido

Esta fase no incluye PostgreSQL operativo, FastAPI, Next.js, OAuth, importadores reales, Séneca, Google Workspace ni Identity Vault. Se incorporarán únicamente después de validar el solver.

## Deuda técnica introducida

- El dataset representa una jornada prototipo y no todavía una semana completa.
- La compatibilidad docente-grupo es binaria; faltan requisitos por materia/perfil.
- La equidad usa inicialmente el contador histórico, no ventanas semanal/mensual/trimestral.
- Las explicaciones describen la alternativa elegida, pero todavía no enumeran candidatos descartados.
