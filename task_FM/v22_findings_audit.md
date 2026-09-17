# v22 Findings 存量污染审计

- 生成时间: 2026-09-17 14:15:06
- 扫描范围: 最近 5 个 run 目录的 shared_findings/*.json（按 mtime 取最新 5 个）
- 判定规则: finding 的 content / notes / metrics 任一字段含 "v22" 字样即登记
- **处置策略: 存量污染登记，随新 run 自然稀释，不主动清理 findings 本身**
- 扫描统计: 5 个 run 目录, 共 196 个 finding 文件, 其中 16 个含 v22 污染

| run 目录名 | 文件名 | variant_name | 污染字段 |
|---|---|---|---|
| run_2026-09-17_14-04-14_primary_task_FM | 21aac224-6f7a-4884-bd96-f6ac485f8467_ss_ha_body.json | ss_ha_body | notes+metrics |
| run_2026-09-17_14-04-14_primary_task_FM | 695ec16b-7a3c-4edd-8521-dfc41b33d44e_ss_vor.json | ss_vor | notes |
| run_2026-09-17_14-04-14_primary_task_FM | c6383148-7b3e-4b22-92e3-91a124ff65bc_sr_calendar_cyclical.json | sr_calendar_cyclical | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 00eaf6ab-9b23-4b7b-bbc9-d0d31aba410d_ss_ha_body.json | ss_ha_body | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 0dbaf17a-067d-427a-96e0-6a91b169eaa6_m_vor.json | m_vor | content |
| run_2026-09-17_12-15-51_primary_task_FM | 2bd07f15-04e7-42bf-821e-2d82701902d6_ss_rsi_state.json | ss_rsi_state | content+notes+metrics |
| run_2026-09-17_12-15-51_primary_task_FM | 2d544ccf-fd02-4b19-9873-fa0e37f8db81_sr_calendar_cyclical.json | sr_calendar_cyclical | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 4b29bbac-cc53-42b4-abad-991df9587758_ss_vor.json | ss_vor | notes |
| run_2026-09-17_12-15-51_primary_task_FM | 4b8ccfc3-3bfd-4d19-a00e-bb6f6d9bdafa_rb_vor.json | rb_vor | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 4e4bf91e-b1c5-45ed-ae89-a46ce50f2f63_m_vor.json | m_vor | content+notes+metrics |
| run_2026-09-17_12-15-51_primary_task_FM | 5198d4af-cb1c-4ea2-858b-3c850ea2474e_eg_rsi_state.json | eg_rsi_state | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 60124f73-ed58-477c-8d34-1c296b93065d_m_oi.json | m_oi | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | 83aeb02c-1e31-4c9a-8752-124b98e4d7bc_m_vor.json | m_vor | content+notes+metrics |
| run_2026-09-17_12-15-51_primary_task_FM | a1b5cd54-c945-48eb-af96-5a1602078ef7_ss_bb_squeeze.json | ss_bb_squeeze | content+notes |
| run_2026-09-17_12-15-51_primary_task_FM | c2246f70-7363-4baa-adf7-1bd0921861d3_eg_bb_squeeze.json | eg_bb_squeeze | content+notes+metrics |
| run_2026-09-17_12-15-51_primary_task_FM | dc3ae115-a55f-4772-8262-47a909716387_sr_calendar_cyclical.json | sr_calendar_cyclical | content+notes |
