# ADR 0001 — Usar OR-Tools CP-SAT para sustituciones

## Context
Las ausencias múltiples deben resolverse de forma global, respetando restricciones duras y optimizando preferencias blandas configurables.

## Decision
Usar Google OR-Tools CP-SAT como motor de optimización. El dominio no depende de OR-Tools; la dependencia queda confinada al módulo `solver`.

## Alternatives
- Selección greedy del primer docente libre: simple, pero consume recursos sin visión global.
- Heurística propia: aumenta deuda técnica y dificulta demostrar optimalidad o límites.

## Consequences
El modelo puede expresar cobertura, incompatibilidades y costes de forma explícita. El proyecto asume la dependencia de OR-Tools y deberá medir el rendimiento del modelo en cada ampliación relevante.
