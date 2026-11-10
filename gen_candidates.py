# Generator-only use of zeron-G/worldquant-alpha-research-agent (no BRAIN login/API calls).
import sys, json, re
sys.path.insert(0, "tool")
import alpha_research_pipeline as p
lib = json.load(open("tool/alpha101_ideas.json"))
cands = p.generate_seed_candidates(library=lib, family_filter={"alpha101"}, available_fields=None)
ALLOWED_FIELDS = {"close","open","high","low","volume","vwap","returns","adv20"}
OPS = {"rank","ts_rank","ts_delta","ts_corr","ts_mean","ts_std_dev","group_neutralize","decay_linear","sign","delta","correlation","ts_sum","ts_min","ts_max","ts_arg_max","ts_arg_min","ts_product","ts_covariance","ts_delay","signed_power","if_else","log","abs","scale","power","min","max","sqrt","ts_zscore","zscore","ts_decay_linear","ts_av_diff","ts_skewness","ts_returns","ts_ir","ts_scale","ts_backfill"}
out=[]
for c in cands:
    e=c.expression
    ids=set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*",e))
    unk=ids-ALLOWED_FIELDS-OPS
    if not unk: out.append({"name":c.idea_name,"expression":e})
json.dump(out,open("candidates.json","w"),indent=1)
open("candidates.txt","w").write("\n".join(o["expression"] for o in out)+"\n")
print(len(cands),"generated;",len(out),"kept (price-volume only)")
