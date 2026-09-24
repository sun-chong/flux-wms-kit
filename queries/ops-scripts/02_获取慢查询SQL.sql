-- ===================================================================
-- 02 获取最近 30 分钟内的慢 SQL（基于 ASH 采样）
-- 注意：GV$ACTIVE_SESSION_HISTORY 需要 Oracle Diagnostics Pack 许可及 DBA 权限
-- “执行时长(S)” = ASH 最后一次采样时间 - SQL 开始执行时间，
--                 仍在执行的语句该值持续增长
-- ===================================================================

SELECT AA.*,
       (SELECT GV.SQL_TEXT
          FROM GV$SQL GV
         WHERE GV.SQL_ID = AA.SQL_ID
           AND ROWNUM <= 1) AS SQLTEXT,
       (SELECT GV2.SQL_TEXT
          FROM GV$SQL GV2
         WHERE GV2.SQL_ID = AA.TOP_LEVEL_SQL_ID
           AND ROWNUM <= 1) AS TOPSQLTEXT,
       (SELECT HT.SQL_TEXT
          FROM DBA_HIST_SQLTEXT HT
         WHERE HT.SQL_ID = AA.SQL_ID
           AND ROWNUM <= 1) AS DBASQLTEXT
  FROM (SELECT A.SESSION_ID,
               A.SQL_EXEC_START AS "开始时间",
               CAST(MAX(A.SAMPLE_TIME) AS DATE) AS "结束时间",
               A.SQL_EXEC_ID,
               A.EVENT,
               A.SQL_ID,
               A.TOP_LEVEL_SQL_ID,
               A.SQL_PLAN_HASH_VALUE,
               (CAST(MAX(A.SAMPLE_TIME) AS DATE) - A.SQL_EXEC_START) * 24 * 60 * 60 AS "执行时长(S)"
          FROM GV$ACTIVE_SESSION_HISTORY A
         WHERE A.SAMPLE_TIME >= SYSDATE - 30 / 24 / 60 -- 查最近 30 分钟内的
           -- 查指定时间段的语句
           -- AND A.SAMPLE_TIME >= TO_DATE('2024-03-21 14:18:00', 'YYYY-MM-DD HH24:MI:SS')
           -- AND A.SAMPLE_TIME <  TO_DATE('2024-03-21 14:20:00', 'YYYY-MM-DD HH24:MI:SS')
           -- 指定存储过程的 SQL_ID
           -- AND A.TOP_LEVEL_SQL_ID = '7jt1btjkcczb8'
           AND A.SQL_ID IS NOT NULL -- 过滤空闲等待事件（无对应 SQL 的采样记录）
           AND A.SQL_EXEC_START IS NOT NULL
         GROUP BY A.SESSION_ID,
                  A.SQL_EXEC_START,
                  A.SQL_EXEC_ID,
                  A.EVENT,
                  A.SQL_ID,
                  A.TOP_LEVEL_SQL_ID,
                  A.SQL_PLAN_HASH_VALUE
         ORDER BY "执行时长(S)" DESC) AA;
