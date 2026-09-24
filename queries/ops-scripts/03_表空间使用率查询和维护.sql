-- ===================================================================
-- 03 表空间使用率查询和维护
-- ===================================================================

-- 查看数据库表空间文件
SELECT *
  FROM DBA_DATA_FILES;

-- 查看所有永久表空间的总容量
-- DBA_DATA_FILES 不含临时表空间
SELECT D.TABLESPACE_NAME,
       SUM(D.BYTES) / 1024 / 1024 AS MB
  FROM DBA_DATA_FILES D
 GROUP BY D.TABLESPACE_NAME;

-- 查看表空间使用率（包含临时表空间）
-- 注意：表空间完全用满时 DBA_FREE_SPACE 中无剩余空间记录，此查询会漏掉该表空间，
--       可参考下方“含自动扩展”的查询（其对该情形做了外连接处理）
SELECT *
  FROM (SELECT A.TABLESPACE_NAME,
               (A.BYTES - B.BYTES) AS "表空间使用大小(BYTE)",
               A.BYTES / (1024 * 1024 * 1024) AS "表空间大小(GB)",
               B.BYTES / (1024 * 1024 * 1024) AS "表空间剩余大小(GB)",
               (A.BYTES - B.BYTES) / (1024 * 1024 * 1024) AS "表空间使用大小(GB)",
               TO_CHAR((1 - B.BYTES / A.BYTES) * 100, '99.99999') || '%' AS "使用率"
          FROM (SELECT TABLESPACE_NAME, SUM(BYTES) AS BYTES
                  FROM DBA_DATA_FILES
                 GROUP BY TABLESPACE_NAME) A,
               (SELECT TABLESPACE_NAME, SUM(BYTES) AS BYTES
                  FROM DBA_FREE_SPACE
                 GROUP BY TABLESPACE_NAME) B
         WHERE A.TABLESPACE_NAME = B.TABLESPACE_NAME
         UNION ALL
         SELECT C.TABLESPACE_NAME,
                D.BYTES_USED AS "表空间使用大小(BYTE)",
                C.BYTES / (1024 * 1024 * 1024) AS "表空间大小(GB)",
                (C.BYTES - D.BYTES_USED) / (1024 * 1024 * 1024) AS "表空间剩余大小(GB)",
                D.BYTES_USED / (1024 * 1024 * 1024) AS "表空间使用大小(GB)",
                TO_CHAR(D.BYTES_USED * 100 / C.BYTES, '99.99999') || '%' AS "使用率"
           FROM (SELECT TABLESPACE_NAME, SUM(BYTES) AS BYTES
                   FROM DBA_TEMP_FILES
                  GROUP BY TABLESPACE_NAME) C,
                (SELECT TABLESPACE_NAME, SUM(BYTES_CACHED) AS BYTES_USED
                   FROM V$TEMP_EXTENT_POOL
                  GROUP BY TABLESPACE_NAME) D
          WHERE C.TABLESPACE_NAME = D.TABLESPACE_NAME)
 ORDER BY TABLESPACE_NAME;

-- 查看数据库表空间使用率（含自动扩展）
SELECT D.TABLESPACE_NAME,
       ROUND(D.MAXSPACE / (1024 * 1024 * 1024), 2) || 'G' AS MAXSPACE,
       ROUND(D.SPACE / (1024 * 1024 * 1024), 2) || 'G' AS SPACE,
       ROUND(F.FREE_SPACE / (1024 * 1024 * 1024), 2) || 'G' AS FREE_SPACE,
       ROUND((D.SPACE - NVL(F.FREE_SPACE, 0)) / DECODE(D.MAXSPACE, 0, NULL, D.MAXSPACE) * 100, 2) || '%' AS USE_RATE
  FROM (SELECT TABLESPACE_NAME,
               SUM(BYTES) AS SPACE,
               SUM(BLOCKS) AS BLOCKS,
               SUM(GREATEST(MAXBYTES, BYTES)) AS MAXSPACE
          FROM DBA_DATA_FILES T
         GROUP BY TABLESPACE_NAME) D,
       (SELECT TABLESPACE_NAME, SUM(BYTES) AS FREE_SPACE
          FROM DBA_FREE_SPACE
         GROUP BY TABLESPACE_NAME) F
 WHERE D.TABLESPACE_NAME = F.TABLESPACE_NAME(+);

-- 查看具体表的占用空间大小
SELECT *
  FROM (SELECT T.TABLESPACE_NAME,
               T.OWNER,
               T.SEGMENT_NAME,
               T.SEGMENT_TYPE,
               SUM(T.BYTES / 1024 / 1024) AS MB
          FROM DBA_SEGMENTS T
         WHERE T.SEGMENT_TYPE = 'TABLE'
         GROUP BY T.TABLESPACE_NAME, T.OWNER, T.SEGMENT_NAME, T.SEGMENT_TYPE) T
 ORDER BY T.MB DESC;

-- 开启数据文件自动扩展 / 调整数据文件大小
-- 注意：路径需替换为实际 dbf 文件路径（可从 DBA_DATA_FILES 查询）
--       RESIZE 不能小于文件已用大小
ALTER DATABASE DATAFILE '...\system_01.dbf' AUTOEXTEND ON;
ALTER DATABASE DATAFILE '...\system_01.dbf' RESIZE 1024 M;

-- 增加数据文件
ALTER TABLESPACE TBS_WMS_PROD ADD DATAFILE '/data/app/oracle/oradata/orcl/TBS_WMS_PROD_04.dbf' SIZE 500M AUTOEXTEND ON NEXT 100M MAXSIZE 32764M;
