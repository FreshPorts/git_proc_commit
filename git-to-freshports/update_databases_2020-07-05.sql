-- required for git

begin;
ALTER TABLE public.commit_log_elements
   DROP CONSTRAINT commit_log_elements_change_type;

ALTER TABLE public.commit_log_elements
    ADD CONSTRAINT commit_log_elements_change_type CHECK (change_type = 'A'::bpchar OR change_type = 'M'::bpchar OR change_type = 'R'::bpchar OR change_type = 'r'::bpchar);

COMMENT ON CONSTRAINT commit_log_elements_change_type ON  public.commit_log_elements IS '
A - add
M - modify
R - remove for subersion, delete for git
r - rename (added for git)';

commit;
