import postgres from "postgres";

const sql = postgres(process.env.DATABASE_URL!, {
  ssl: "require",
  max: 1,
  prepare: false,
});

export default sql;
