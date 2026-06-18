# ADR-0021 — Critic Self-Challenge + Métriques Anti-Biais

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis

## Contexte

Le Critic Engine est un organe central de l'agent : il challenge chaque finding, plan, et fix. Mais personne ne challenge le Critic lui-même.

Risques identifiés :
- **#5** Le Critic peut devenir trop lax si l'humain override 50% de ses rejets → drift silencieux
- **#30** Pas de méta-critic → un bug du Critic passe inaperçu
- **#32** Pas de signal d'arrêt → si 0 findings pendant 6 mois, c'est peut-être le Critic qui est mort

## Décision

**Critic self-challenge = 4 mécanismes complémentaires** :

### Mécanisme 1 — Calibration empirique (Layer 7)

Le scoring du Critic est **empirique**, pas théorique :

```python
# critic_calibration.py
class CriticCalibrator:
    """Recalibre le scoring du Critic à partir du feedback réel."""

    def recalibrate(self, feedback_window_days: int = 90) -> CalibrationReport:
        """
        Lit le feedback.json des N derniers jours.
        Pour chaque finding rejetée par le Critic puis acceptée par l'humain :
            - Le Critic a fait un faux négatif → ajuste le seuil
        Pour chaque finding acceptée par le Critic puis rejetée par l'humain :
            - Le Critic a fait un faux positif → ajuste le seuil
        """
        ...
```

Output : nouveaux seuils par tier, persistés dans le KG.

### Mécanisme 2 — Confidence tiers nommés (V1.2)

Au lieu de seuils arbitraires (0.6, 0.7), des **tiers explicites** :

```
tier_0: confidence < 0.4   → REJET AUTOMATIQUE par le Critic
tier_1: 0.4 ≤ confidence < 0.7 → REVUE HUMAINE OBLIGATOIRE
tier_2: confidence ≥ 0.7   → ACCEPTATION DIRECTE (critic optionnel)
```

Justification : 0.4 / 0.7 sont des **chiffres ronds** qui correspondent à des seuils psychologiques (biais d'ancrage). Plus explicites que 0.6 / 0.85.

### Mécanisme 3 — Override tracking (Layer 5)

Chaque override humain (accepter un finding rejeté par le Critic) est tracé :

```json
{
  "override_id": "uuid",
  "finding_id": "f-001",
  "critic_decision": "rejected",
  "critic_reason": "confidence < 0.6, no concrete evidence",
  "human_decision": "accepted",
  "human_reason": "I know this codebase, this is a real issue, the LLM missed the context",
  "timestamp": "2026-06-17T...",
  "pattern": "domain:code, subcategory:complexity"
}
```

Métriques dérivées :
- `override_rate_by_pattern` : % de rejets override par pattern
- Si > 30% → alerte : le Critic est trop strict sur ce pattern
- Si < 5% pendant 6 mois → alerte : le Critic est inutile

### Mécanisme 4 — Méta-critic périodique (Layer 7)

Un audit mensuel du Critic lui-même :

```python
# meta_critic.py
class MetaCritic:
    """Audite le Critic Engine sur la période écoulée."""

    def audit(self, period_days: int = 30) -> MetaReport:
        findings_in_period = kg.get_findings_since(period_days)
        for finding in findings_in_period:
            critic_decision = finding.critic_decision
            human_outcome = finding.human_outcome  # accepted/rejected/pending
            if critic_decision == "rejected" and human_outcome == "accepted":
                # False negative
                self.report.add(false_negative(finding))
            elif critic_decision == "accepted" and human_outcome == "rejected":
                # False positive
                self.report.add(false_positive(finding))
        return self.report
```

Si false_negative_rate > 25% → alerte "Critic trop strict"
Si false_positive_rate > 25% → alerte "Critic trop lax"

### Mécanisme 5 — Kill switch (V3)

Si le Critic accumule trop d'erreurs, il peut être **temporairement désactivé** :

```yaml
# .critic-config.yaml
critic:
  enabled: true
  kill_switch:
    false_negative_rate_threshold: 0.30
    false_positive_rate_threshold: 0.30
    auto_disable: true  # désactivation auto si seuils dépassés
    manual_re_enable_required: true  # l'humain doit le réactiver
```

## Conséquences

### Positives

- **Critic reste aligné avec la réalité** : recalibrage continu sur feedback
- **Drift détecté tôt** : le méta-critic alerte avant que le Critic devienne inutile
- **Pas de "mort silencieuse"** : si 0 findings pendant X mois, signal d'alerte
- **Override tracé** : l'humain peut re-évaluer ses propres décisions

### Négatives / Trade-offs

- **Recalibrage peut introduire de l'instabilité** : si le feedback est biaisé (e.g. humain fatigue), le scoring oscille
  - Mitigation : lissage exponentiel sur le recalibrage (pas de changement brutal)
- **Méta-critic ajoute de la complexité** : un module de plus à maintenir
  - Acceptable : c'est le Critic qui s'audite, c'est sa raison d'être
- **Override tracking peut être perçu comme "Big Brother"** : l'humain est tracé
  - Mitigation : les logs sont locaux, jamais transmis à un serveur externe

## Critères d'acceptation

- [ ] Test : injecter 100 findings, override 50%, recalibrage → seuils ajustés
- [ ] Test : 0 findings pendant 6 mois → alerte générée
- [ ] Test : override_rate > 30% sur un pattern → alerte générée
- [ ] Test : Critic kill switch → désactivation, reactivation manuelle
- [ ] Documentation utilisateur à jour sur les overrides (pas de "Big Brother")

## Liens

- ADR-0017 (architecture)
- ADR-0018 (threat model)
