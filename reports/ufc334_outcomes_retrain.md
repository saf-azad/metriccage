# UFC 334: Gane vs. Hokit — top outcomes and probability trees

Source: `ufc334_predictions_retrain.json`. Joint outcome = P(winner) × P(method); the method split is the same for both fighters.

## Top 3 outcomes per fight

| Bout | #1 | #2 | #3 |
|---|---|---|---|
| Ciryl Gane vs Josh Hokit | Gane by Decision 30.0% | Hokit by Decision 23.2% | Gane by KO/TKO 15.5% |
| Kayla Harrison vs Amanda Nunes | Nunes by Decision 32.4% | Nunes by KO/TKO 18.5% | Harrison by Decision 17.6% |
| Caio Borralho vs Yousri Belgaroui | Borralho by Decision 24.7% | Borralho by KO/TKO 19.3% | Belgaroui by Decision 19.1% |
| Kevin Holland vs Uros Medic | Holland by Decision 30.4% | Medic by Decision 23.5% | Holland by KO/TKO 15.7% |
| Luis Gurule vs Bilal Hasan | Hasan by Decision 31.9% | Hasan by KO/TKO 24.9% | Hasan by Submission 15.9% |
| Stephen Thompson vs Charles Radtke | Radtke by Decision 31.9% | Radtke by KO/TKO 18.8% | Thompson by Decision 17.3% |
| Drew Dober vs Chris Duncan | Duncan by KO/TKO 48.7% | Dober by KO/TKO 26.4% | Duncan by Submission 16.1% |
| Jim Miller vs Terrance McKinney | McKinney by Decision 27.4% | McKinney by KO/TKO 21.5% | McKinney by Submission 15.9% |
| Cesar Almeida vs Donte Johnson | Johnson by Decision 29.5% | Johnson by KO/TKO 28.5% | Johnson by Submission 14.8% |
| Jared Gordon vs Melquizael Costa | Costa by Decision 35.0% | Costa by KO/TKO 19.2% | Gordon by Decision 17.5% |
| Macy Chiasson vs Bia Mesquita | Mesquita by Decision 30.8% | Mesquita by KO/TKO 18.1% | Chiasson by Decision 16.7% |
| Alatengheili vs Juan Diaz | Diaz by Decision 31.9% | Diaz by KO/TKO 18.8% | Alatengheili by Decision 17.3% |
| Evan Elder vs Samuel Sanches | Elder by Decision 28.3% | Sanches by Decision 21.9% | Elder by KO/TKO 16.6% |

## Probability trees

### Ciryl Gane vs Josh Hokit (Heavyweight, main card)

```
├─ Ciryl Gane wins  56.4%
│  ├─ by Decision    53.1% of the time  →  30.0% overall
│  ├─ by KO/TKO      27.4% of the time  →  15.5% overall
│  └─ by Submission  19.4% of the time  →  10.9% overall
└─ Josh Hokit wins  43.6%
   ├─ by Decision    53.1% of the time  →  23.2% overall
   ├─ by KO/TKO      27.4% of the time  →  12.0% overall
   └─ by Submission  19.4% of the time  →   8.5% overall
When it ends: R1 19% · R2 14% · R3 7% · R4 5% · R5 2% · goes to decision 53%
```

### Kayla Harrison vs Amanda Nunes (Women's Bantamweight, main card)

```
├─ Amanda Nunes wins  64.8%
│  ├─ by Decision    50.0% of the time  →  32.4% overall
│  ├─ by KO/TKO      28.5% of the time  →  18.5% overall
│  └─ by Submission  21.5% of the time  →  13.9% overall
└─ Kayla Harrison wins  35.2%
   ├─ by Decision    50.0% of the time  →  17.6% overall
   ├─ by KO/TKO      28.5% of the time  →  10.0% overall
   └─ by Submission  21.5% of the time  →   7.6% overall
When it ends: R1 20% · R2 15% · R3 8% · R4 5% · R5 3% · goes to decision 50%
```

### Caio Borralho vs Yousri Belgaroui (Middleweight, main card)

```
├─ Caio Borralho wins  56.4%
│  ├─ by Decision    43.8% of the time  →  24.7% overall
│  ├─ by KO/TKO      34.3% of the time  →  19.3% overall
│  └─ by Submission  21.9% of the time  →  12.3% overall
└─ Yousri Belgaroui wins  43.6%
   ├─ by Decision    43.8% of the time  →  19.1% overall
   ├─ by KO/TKO      34.3% of the time  →  15.0% overall
   └─ by Submission  21.9% of the time  →   9.6% overall
When it ends: R1 22% · R2 17% · R3 8% · R4 6% · R5 3% · goes to decision 44%
```

### Kevin Holland vs Uros Medic (Welterweight, main card)

```
├─ Kevin Holland wins  56.4%
│  ├─ by Decision    54.0% of the time  →  30.4% overall
│  ├─ by KO/TKO      27.9% of the time  →  15.7% overall
│  └─ by Submission  18.1% of the time  →  10.2% overall
└─ Uros Medic wins  43.6%
   ├─ by Decision    54.0% of the time  →  23.5% overall
   ├─ by KO/TKO      27.9% of the time  →  12.2% overall
   └─ by Submission  18.1% of the time  →   7.9% overall
When it ends: R1 18% · R2 14% · R3 7% · R4 5% · R5 2% · goes to decision 54%
```

### Luis Gurule vs Bilal Hasan (Flyweight, main card)

```
├─ Bilal Hasan wins  72.7%
│  ├─ by Decision    43.8% of the time  →  31.9% overall
│  ├─ by KO/TKO      34.3% of the time  →  24.9% overall
│  └─ by Submission  21.9% of the time  →  15.9% overall
└─ Luis Gurule wins  27.3%
   ├─ by Decision    43.8% of the time  →  11.9% overall
   ├─ by KO/TKO      34.3% of the time  →   9.4% overall
   └─ by Submission  21.9% of the time  →   6.0% overall
When it ends: R1 22% · R2 17% · R3 8% · R4 6% · R5 3% · goes to decision 44%
```

### Stephen Thompson vs Charles Radtke (Welterweight, prelim card)

```
├─ Charles Radtke wins  64.8%
│  ├─ by Decision    49.2% of the time  →  31.9% overall
│  ├─ by KO/TKO      28.9% of the time  →  18.8% overall
│  └─ by Submission  21.8% of the time  →  14.2% overall
└─ Stephen Thompson wins  35.2%
   ├─ by Decision    49.2% of the time  →  17.3% overall
   ├─ by KO/TKO      28.9% of the time  →  10.2% overall
   └─ by Submission  21.8% of the time  →   7.7% overall
When it ends: R1 20% · R2 15% · R3 8% · R4 5% · R5 3% · goes to decision 49%
```

### Drew Dober vs Chris Duncan (Lightweight, prelim card)

```
├─ Chris Duncan wins  64.8%
│  ├─ by KO/TKO      75.1% of the time  →  48.7% overall
│  ├─ by Submission  24.9% of the time  →  16.1% overall
│  └─ by Decision     0.0% of the time  →   0.0% overall
└─ Drew Dober wins  35.2%
   ├─ by KO/TKO      75.1% of the time  →  26.4% overall
   ├─ by Submission  24.9% of the time  →   8.7% overall
   └─ by Decision     0.0% of the time  →   0.0% overall
When it ends: R1 40% · R2 30% · R3 15% · R4 10% · R5 5%
```

### Jim Miller vs Terrance McKinney (Lightweight, prelim card)

```
├─ Terrance McKinney wins  64.8%
│  ├─ by Decision    42.3% of the time  →  27.4% overall
│  ├─ by KO/TKO      33.1% of the time  →  21.5% overall
│  └─ by Submission  24.6% of the time  →  15.9% overall
└─ Jim Miller wins  35.2%
   ├─ by Decision    42.3% of the time  →  14.9% overall
   ├─ by KO/TKO      33.1% of the time  →  11.7% overall
   └─ by Submission  24.6% of the time  →   8.6% overall
When it ends: R1 23% · R2 17% · R3 9% · R4 6% · R5 3% · goes to decision 42%
```

### Cesar Almeida vs Donte Johnson (Catch Weight, prelim card)

```
├─ Donte Johnson wins  72.7%
│  ├─ by Decision    40.6% of the time  →  29.5% overall
│  ├─ by KO/TKO      39.2% of the time  →  28.5% overall
│  └─ by Submission  20.3% of the time  →  14.8% overall
└─ Cesar Almeida wins  27.3%
   ├─ by Decision    40.6% of the time  →  11.1% overall
   ├─ by KO/TKO      39.2% of the time  →  10.7% overall
   └─ by Submission  20.3% of the time  →   5.5% overall
When it ends: R1 24% · R2 18% · R3 9% · R4 6% · R5 3% · goes to decision 41%
```

### Jared Gordon vs Melquizael Costa (Lightweight, prelim card)

```
├─ Melquizael Costa wins  66.7%
│  ├─ by Decision    52.5% of the time  →  35.0% overall
│  ├─ by KO/TKO      28.8% of the time  →  19.2% overall
│  └─ by Submission  18.7% of the time  →  12.5% overall
└─ Jared Gordon wins  33.3%
   ├─ by Decision    52.5% of the time  →  17.5% overall
   ├─ by KO/TKO      28.8% of the time  →   9.6% overall
   └─ by Submission  18.7% of the time  →   6.2% overall
When it ends: R1 19% · R2 14% · R3 7% · R4 5% · R5 2% · goes to decision 53%
```

### Macy Chiasson vs Bia Mesquita (Women's Bantamweight, prelim card)

```
├─ Bia Mesquita wins  64.8%
│  ├─ by Decision    47.4% of the time  →  30.8% overall
│  ├─ by KO/TKO      27.9% of the time  →  18.1% overall
│  └─ by Submission  24.7% of the time  →  16.0% overall
└─ Macy Chiasson wins  35.2%
   ├─ by Decision    47.4% of the time  →  16.7% overall
   ├─ by KO/TKO      27.9% of the time  →   9.8% overall
   └─ by Submission  24.7% of the time  →   8.7% overall
When it ends: R1 21% · R2 16% · R3 8% · R4 5% · R5 3% · goes to decision 47%
```

### Alatengheili vs Juan Diaz (Bantamweight, prelim card)

```
├─ Juan Diaz wins  64.8%
│  ├─ by Decision    49.2% of the time  →  31.9% overall
│  ├─ by KO/TKO      28.9% of the time  →  18.8% overall
│  └─ by Submission  21.8% of the time  →  14.2% overall
└─ Alatengheili wins  35.2%
   ├─ by Decision    49.2% of the time  →  17.3% overall
   ├─ by KO/TKO      28.9% of the time  →  10.2% overall
   └─ by Submission  21.8% of the time  →   7.7% overall
When it ends: R1 20% · R2 15% · R3 8% · R4 5% · R5 3% · goes to decision 49%
```

### Evan Elder vs Samuel Sanches (Lightweight, prelim card)

```
├─ Evan Elder wins  56.4%
│  ├─ by Decision    50.1% of the time  →  28.3% overall
│  ├─ by KO/TKO      29.5% of the time  →  16.6% overall
│  └─ by Submission  20.4% of the time  →  11.5% overall
└─ Samuel Sanches wins  43.6%
   ├─ by Decision    50.1% of the time  →  21.9% overall
   ├─ by KO/TKO      29.5% of the time  →  12.9% overall
   └─ by Submission  20.4% of the time  →   8.9% overall
When it ends: R1 20% · R2 15% · R3 7% · R4 5% · R5 2% · goes to decision 50%
```
