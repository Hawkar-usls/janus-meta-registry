unit fo3edit_vault112_per_lounger_backend_shard_export_v2_0;

{
  JANUS / Fallout 3
  Vault 112 per-lounger backend-shard exporter v2.0

  Read-only. Load exactly the six official Fallout 3 masters.

  Goal:
    Recover the asset-level path
      James monitor -> James Visiontron -> per-lounger hardware shard
      -> linked/referencing backend state -> memory/carrier candidate
    without treating the static Dad monitor NOTE assets as memory storage.

  Exact Visiontron base FormIDs used as anchors:
    0002A45B
    000B364C
    000B06D4 (broken)

  James-specific monitor base:
    00031190 Vault112PodTermDad

  Outputs:
    JANUS-Vault112a-Backend-Hardware-v2.0.tsv
    JANUS-Vault112a-Backend-Hardware-Links-v2.0.tsv
    JANUS-Vault112a-Backend-Hardware-Reverse-Refs-v2.0.tsv
    JANUS-ThinkMachine-Backend-Semantic-Candidates-v2.0.tsv

  Spatial association is discovery evidence only. Nearest != functional binding.
}

var
  HardwareOut: TStringList;
  LinkOut: TStringList;
  ReverseOut: TStringList;
  SemanticOut: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  SeenLogical: TStringList;
  SemanticTerms: TStringList;
  Blocked: boolean;
  DuplicateLogicalCount: integer;

function CleanTSV(s: string): string;
begin
  s := StringReplace(s, #9, ' ', [rfReplaceAll]);
  s := StringReplace(s, #13, ' ', [rfReplaceAll]);
  s := StringReplace(s, #10, ' ', [rfReplaceAll]);
  Result := s;
end;

function Hex8(v: cardinal): string;
begin
  Result := IntToHex(v, 8);
end;

function Lower(s: string): string;
begin
  Result := LowerCase(s);
end;

function FloatInvariant(v: double): string;
begin
  Result := FloatToStr(v);
  Result := StringReplace(Result, ',', '.', [rfReplaceAll]);
end;

function BoolText(v: boolean): string;
begin
  if v then Result := 'true' else Result := 'false';
end;

function EndsWithText(s, suffix: string): boolean;
var
  n, m: integer;
begin
  n := Length(s);
  m := Length(suffix);
  if n < m then begin
    Result := false;
    exit;
  end;
  Result := CompareText(Copy(s, n - m + 1, m), suffix) = 0;
end;

function IsPluginFilename(fn: string): boolean;
begin
  Result := EndsWithText(fn, '.esm') or EndsWithText(fn, '.esp');
end;

function IsOfficialMaster(fn: string): boolean;
begin
  Result :=
    (CompareText(fn, 'Fallout3.esm') = 0) or
    (CompareText(fn, 'Anchorage.esm') = 0) or
    (CompareText(fn, 'ThePitt.esm') = 0) or
    (CompareText(fn, 'BrokenSteel.esm') = 0) or
    (CompareText(fn, 'PointLookout.esm') = 0) or
    (CompareText(fn, 'Zeta.esm') = 0);
end;

function IsVisiontronBase(id: cardinal): boolean;
begin
  Result := (id = $0002A45B) or (id = $000B364C) or (id = $000B06D4);
end;

function EffectiveWinning(e: IInterface): IInterface;
var
  root: IInterface;
begin
  Result := nil;
  if not Assigned(e) then exit;
  if ElementType(e) <> etMainRecord then exit;
  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  Result := WinningOverride(root);
  if not Assigned(Result) then Result := root;
  if GetIsDeleted(Result) then Result := nil;
end;

function CanonicalCellEditorID(e: IInterface): string;
var
  c, rootCell: IInterface;
begin
  Result := '';
  c := GetContainer(e);
  while Assigned(c) do begin
    if (ElementType(c) = etMainRecord) and (Signature(c) = 'CELL') then begin
      rootCell := MasterOrSelf(c);
      if not Assigned(rootCell) then rootCell := c;
      Result := EditorID(rootCell);
      exit;
    end;
    c := GetContainer(c);
  end;
end;

function FirstNonEmpty(a, b, c: string): string;
begin
  Result := a;
  if Result = '' then Result := b;
  if Result = '' then Result := c;
end;

function SafePathValue(e: IInterface; path: string): string;
var
  x: IInterface;
begin
  Result := '';
  if not Assigned(e) then exit;
  x := ElementByPath(e, path);
  if Assigned(x) then Result := CleanTSV(GetEditValue(x));
end;

function IdentityText(base, ref: IInterface): string;
begin
  Result := Lower(
    EditorID(base) + ' ' + Name(base) + ' ' +
    EditorID(ref) + ' ' + Name(ref)
  );
end;

function HardwareKind(base, ref: IInterface): string;
var
  fixed: cardinal;
  sig, t: string;
begin
  Result := 'OTHER';
  fixed := FixedFormID(MasterOrSelf(base));
  sig := Signature(base);
  t := IdentityText(base, ref);

  if fixed = $00031190 then begin
    Result := 'JAMES_MONITOR';
    exit;
  end;
  if IsVisiontronBase(fixed) then begin
    Result := 'VISIONTRON';
    exit;
  end;
  if sig = 'TERM' then begin
    Result := 'TERMINAL';
    exit;
  end;
  if (Pos('computer', t) > 0) or
     (Pos('console', t) > 0) or
     (Pos('processor', t) > 0) or
     (Pos('mainframe', t) > 0) or
     (Pos('think machine', t) > 0) or
     (Pos('visiontron', t) > 0) then begin
    Result := 'COMPUTER_IDENTITY';
    exit;
  end;
end;

procedure AddSemanticTerms;
begin
  SemanticTerms.Add('think machine');
  SemanticTerms.Add('3600r');
  SemanticTerms.Add('visiontron');
  SemanticTerms.Add('memory');
  SemanticTerms.Add('mem chip');
  SemanticTerms.Add('memory chip');
  SemanticTerms.Add('memchip');
  SemanticTerms.Add('neural');
  SemanticTerms.Add('resident');
  SemanticTerms.Add('user unknown');
  SemanticTerms.Add('archive');
  SemanticTerms.Add('persist');
  SemanticTerms.Add('restore');
  SemanticTerms.Add('reload');
  SemanticTerms.Add('snapshot');
  SemanticTerms.Add('storage');
  SemanticTerms.Add('buffer');
  SemanticTerms.Add('cache');
  SemanticTerms.Add('slot');
  SemanticTerms.Add('sync');
  SemanticTerms.Add('synchron');
  SemanticTerms.Add('transfer');
  SemanticTerms.Add('serialize');
  SemanticTerms.Add('copy');
  SemanticTerms.Add('write');
end;

function FindSemanticTerm(text: string): string;
var
  i: integer;
  t: string;
begin
  Result := '';
  t := Lower(text);
  for i := 0 to SemanticTerms.Count - 1 do begin
    if Pos(SemanticTerms[i], t) > 0 then begin
      Result := SemanticTerms[i];
      exit;
    end;
  end;
end;

procedure EmitLinkedLeaf(ownerRec, el: IInterface; ownerKind, ownerScope: string; depth: integer);
var
  i, n: integer;
  child, linked, rootLinked: IInterface;
  value, linkedFile, linkedSig, linkedForm, linkedEDID, linkedName: string;
begin
  if not Assigned(el) then exit;
  if depth > 40 then exit;
  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then EmitLinkedLeaf(ownerRec, child, ownerKind, ownerScope, depth + 1);
    end;
    exit;
  end;

  value := GetEditValue(el);
  if value = '' then exit;
  linked := LinksTo(el);
  linkedFile := '';
  linkedSig := '';
  linkedForm := '';
  linkedEDID := '';
  linkedName := '';
  if Assigned(linked) then begin
    rootLinked := MasterOrSelf(linked);
    if not Assigned(rootLinked) then rootLinked := linked;
    linkedFile := GetFileName(GetFile(rootLinked));
    linkedSig := Signature(rootLinked);
    linkedForm := Hex8(GetLoadOrderFormID(rootLinked));
    linkedEDID := EditorID(rootLinked);
    linkedName := Name(rootLinked);
  end;

  { Keep only semantically useful leaves or actual form links. }
  if (linkedForm = '') and
     (FindSemanticTerm(Name(el) + ' ' + value) = '') and
     (Pos('script', Lower(Name(el))) = 0) and
     (Pos('enable', Lower(Name(el))) = 0) and
     (Pos('owner', Lower(Name(el))) = 0) then exit;

  if Length(value) > 8192 then value := Copy(value, 1, 8192) + '...[TRUNCATED]';
  LinkOut.Add(
    CleanTSV(ownerScope) + #9 + CleanTSV(ownerKind) + #9 +
    CleanTSV(GetFileName(GetFile(ownerRec))) + #9 +
    CleanTSV(Signature(ownerRec)) + #9 + Hex8(GetLoadOrderFormID(ownerRec)) + #9 +
    CleanTSV(EditorID(ownerRec)) + #9 + CleanTSV(Name(ownerRec)) + #9 +
    CleanTSV(Path(el)) + #9 + CleanTSV(Name(el)) + #9 + CleanTSV(value) + #9 +
    CleanTSV(linkedFile) + #9 + CleanTSV(linkedSig) + #9 + CleanTSV(linkedForm) + #9 +
    CleanTSV(linkedEDID) + #9 + CleanTSV(linkedName)
  );
end;

procedure EmitReverseRefs(anchorRec: IInterface; anchorScope, anchorKind: string);
var
  root, r: IInterface;
  i, n: integer;
begin
  root := MasterOrSelf(anchorRec);
  if not Assigned(root) then root := anchorRec;
  n := ReferencedByCount(root);
  for i := 0 to n - 1 do begin
    r := ReferencedByIndex(root, i);
    if not Assigned(r) then continue;
    if not IsOfficialMaster(GetFileName(GetFile(r))) then continue;
    ReverseOut.Add(
      CleanTSV(anchorScope) + #9 + CleanTSV(anchorKind) + #9 +
      CleanTSV(GetFileName(GetFile(root))) + #9 + CleanTSV(Signature(root)) + #9 +
      Hex8(GetLoadOrderFormID(root)) + #9 + CleanTSV(EditorID(root)) + #9 + CleanTSV(Name(root)) + #9 +
      CleanTSV(GetFileName(GetFile(r))) + #9 + CleanTSV(Signature(r)) + #9 +
      Hex8(GetLoadOrderFormID(r)) + #9 + CleanTSV(EditorID(r)) + #9 + CleanTSV(Name(r)) + #9 +
      CleanTSV(FullPath(r))
    );
  end;
end;

procedure ExportHardwareRef(rec: IInterface);
var
  base, rootBase, rootRef: IInterface;
  kind: string;
  p: TwbVector;
  fixed: cardinal;
  enableRaw, ownerRaw, refScriptRaw, baseScriptRaw: string;
begin
  base := BaseRecord(rec);
  if not Assigned(base) then exit;
  rootBase := MasterOrSelf(base);
  if not Assigned(rootBase) then rootBase := base;
  rootRef := MasterOrSelf(rec);
  if not Assigned(rootRef) then rootRef := rec;
  kind := HardwareKind(rootBase, rec);
  if kind = 'OTHER' then exit;

  fixed := FixedFormID(rootBase);
  p := GetPosition(rec);
  enableRaw := FirstNonEmpty(
    SafePathValue(rec, 'XESP - Enable Parent\Reference'),
    SafePathValue(rec, 'Enable Parent\Reference'),
    SafePathValue(rec, 'XESP\Reference')
  );
  ownerRaw := FirstNonEmpty(
    SafePathValue(rec, 'XOWN - Owner'),
    SafePathValue(rec, 'Ownership\Owner'),
    SafePathValue(rec, 'Ownership')
  );
  refScriptRaw := FirstNonEmpty(SafePathValue(rec, 'SCRI - Script'), SafePathValue(rec, 'Script'), '');
  baseScriptRaw := FirstNonEmpty(SafePathValue(rootBase, 'SCRI - Script'), SafePathValue(rootBase, 'Script'), '');

  HardwareOut.Add(
    Hex8(GetLoadOrderFormID(rootRef)) + #9 + CleanTSV(GetFileName(GetFile(rec))) + #9 +
    CleanTSV(kind) + #9 + CleanTSV(Signature(rootBase)) + #9 + Hex8(fixed) + #9 +
    CleanTSV(EditorID(rootBase)) + #9 + CleanTSV(Name(rootBase)) + #9 +
    FloatInvariant(p.x) + #9 + FloatInvariant(p.y) + #9 + FloatInvariant(p.z) + #9 +
    BoolText(GetIsInitiallyDisabled(rec)) + #9 + CleanTSV(enableRaw) + #9 + CleanTSV(ownerRaw) + #9 +
    CleanTSV(refScriptRaw) + #9 + CleanTSV(baseScriptRaw) + #9 + CleanTSV(FullPath(rec))
  );

  EmitLinkedLeaf(rec, rec, kind, 'PLACED_REF', 0);
  EmitLinkedLeaf(rootBase, rootBase, kind, 'BASE_RECORD', 0);
  EmitReverseRefs(rootRef, 'PLACED_REF', kind);
  EmitReverseRefs(rootBase, 'BASE_RECORD', kind);
end;

procedure ScanSemanticLeaves(rec, el: IInterface; depth: integer);
var
  i, n: integer;
  child, linked, root: IInterface;
  value, term, linkedFile, linkedSig, linkedForm, linkedEDID: string;
begin
  if not Assigned(el) then exit;
  if depth > 32 then exit;
  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then ScanSemanticLeaves(rec, child, depth + 1);
    end;
    exit;
  end;

  value := GetEditValue(el);
  if value = '' then exit;
  term := FindSemanticTerm(Name(el) + ' ' + value);
  if term = '' then exit;
  if Length(value) > 8192 then value := Copy(value, 1, 8192) + '...[TRUNCATED]';

  linkedFile := '';
  linkedSig := '';
  linkedForm := '';
  linkedEDID := '';
  linked := LinksTo(el);
  if Assigned(linked) then begin
    root := MasterOrSelf(linked);
    if not Assigned(root) then root := linked;
    linkedFile := GetFileName(GetFile(root));
    linkedSig := Signature(root);
    linkedForm := Hex8(GetLoadOrderFormID(root));
    linkedEDID := EditorID(root);
  end;

  SemanticOut.Add(
    CleanTSV(GetFileName(GetFile(rec))) + #9 + CleanTSV(Signature(rec)) + #9 +
    Hex8(GetLoadOrderFormID(rec)) + #9 + CleanTSV(EditorID(rec)) + #9 + CleanTSV(Name(rec)) + #9 +
    CleanTSV(term) + #9 + CleanTSV(Path(el)) + #9 + CleanTSV(Name(el)) + #9 + CleanTSV(value) + #9 +
    CleanTSV(linkedFile) + #9 + CleanTSV(linkedSig) + #9 + CleanTSV(linkedForm) + #9 + CleanTSV(linkedEDID) + #9 +
    CleanTSV(FullPath(rec))
  );
end;

function Initialize: integer;
var
  i: integer;
  f: IInterface;
  fn: string;
begin
  Result := 0;
  Blocked := false;
  DuplicateLogicalCount := 0;

  HardwareOut := TStringList.Create;
  LinkOut := TStringList.Create;
  ReverseOut := TStringList.Create;
  SemanticOut := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  SeenLogical := TStringList.Create;
  SemanticTerms := TStringList.Create;

  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;
  SeenLogical.Sorted := true;
  SeenLogical.Duplicates := dupIgnore;
  SemanticTerms.Sorted := true;
  SemanticTerms.Duplicates := dupIgnore;
  AddSemanticTerms;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS Vault112 shard v2.0 BLOCKED: xEdit is not running in FO3 mode.');
    Blocked := true;
  end;

  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if not Assigned(f) then continue;
    fn := GetFileName(f);
    if IsOfficialMaster(fn) then LoadedOfficial.Add(fn)
    else if IsPluginFilename(fn) then UnexpectedPlugins.Add(fn);
  end;
  if LoadedOfficial.Count <> 6 then begin
    AddMessage('JANUS Vault112 shard v2.0 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS Vault112 shard v2.0 BLOCKED: non-official plugins loaded.');
    Blocked := true;
  end;

  HardwareOut.Add('logical_ref_formid' + #9 + 'winning_file' + #9 + 'hardware_kind' + #9 + 'base_signature' + #9 + 'base_fixed_formid' + #9 + 'base_editorid' + #9 + 'base_name' + #9 + 'position_x' + #9 + 'position_y' + #9 + 'position_z' + #9 + 'initially_disabled' + #9 + 'enable_parent_raw' + #9 + 'owner_raw' + #9 + 'ref_script_raw' + #9 + 'base_script_raw' + #9 + 'full_path');
  LinkOut.Add('owner_scope' + #9 + 'owner_kind' + #9 + 'owner_file' + #9 + 'owner_signature' + #9 + 'owner_formid' + #9 + 'owner_editorid' + #9 + 'owner_name' + #9 + 'element_path' + #9 + 'element_name' + #9 + 'element_value' + #9 + 'linked_file' + #9 + 'linked_signature' + #9 + 'linked_formid' + #9 + 'linked_editorid' + #9 + 'linked_name');
  ReverseOut.Add('anchor_scope' + #9 + 'anchor_kind' + #9 + 'anchor_file' + #9 + 'anchor_signature' + #9 + 'anchor_formid' + #9 + 'anchor_editorid' + #9 + 'anchor_name' + #9 + 'referencing_file' + #9 + 'referencing_signature' + #9 + 'referencing_formid' + #9 + 'referencing_editorid' + #9 + 'referencing_name' + #9 + 'referencing_full_path');
  SemanticOut.Add('record_file' + #9 + 'record_signature' + #9 + 'record_formid' + #9 + 'record_editorid' + #9 + 'record_name' + #9 + 'matched_term' + #9 + 'element_path' + #9 + 'element_name' + #9 + 'element_value' + #9 + 'linked_file' + #9 + 'linked_signature' + #9 + 'linked_formid' + #9 + 'linked_editorid' + #9 + 'record_full_path');

  AddMessage('JANUS Vault112 per-lounger backend-shard exporter v2.0 initialized.');
end;

function Process(e: IInterface): integer;
var
  win, root: IInterface;
  logicalKey: string;
begin
  Result := 0;
  if Blocked then exit;
  if ElementType(e) <> etMainRecord then exit;
  if not IsOfficialMaster(GetFileName(GetFile(e))) then exit;

  win := EffectiveWinning(e);
  if not Assigned(win) then exit;
  if not IsSameRecord(e, win) then exit;

  root := MasterOrSelf(win);
  if not Assigned(root) then root := win;
  logicalKey := GetFileName(GetFile(root)) + '|' + Hex8(GetLoadOrderFormID(root));
  if SeenLogical.IndexOf(logicalKey) >= 0 then begin
    DuplicateLogicalCount := DuplicateLogicalCount + 1;
    exit;
  end;
  SeenLogical.Add(logicalKey);

  if (Signature(win) = 'REFR') and (CompareText(CanonicalCellEditorID(win), 'Vault112a') = 0) then
    ExportHardwareRef(win);

  ScanSemanticLeaves(win, win, 0);
end;

function Finalize: integer;
var
  hardwareFn, linksFn, reverseFn, semanticFn: string;
begin
  Result := 0;
  if Blocked then begin
    AddMessage('JANUS Vault112 shard v2.0 export NOT WRITTEN: prerequisites failed.');
  end else if DuplicateLogicalCount <> 0 then begin
    AddMessage('JANUS Vault112 shard v2.0 export NOT WRITTEN: duplicate logical records = ' + IntToStr(DuplicateLogicalCount));
  end else begin
    hardwareFn := ScriptsPath + 'JANUS-Vault112a-Backend-Hardware-v2.0.tsv';
    linksFn := ScriptsPath + 'JANUS-Vault112a-Backend-Hardware-Links-v2.0.tsv';
    reverseFn := ScriptsPath + 'JANUS-Vault112a-Backend-Hardware-Reverse-Refs-v2.0.tsv';
    semanticFn := ScriptsPath + 'JANUS-ThinkMachine-Backend-Semantic-Candidates-v2.0.tsv';
    HardwareOut.SaveToFile(hardwareFn);
    LinkOut.SaveToFile(linksFn);
    ReverseOut.SaveToFile(reverseFn);
    SemanticOut.SaveToFile(semanticFn);
    AddMessage('Hardware rows: ' + IntToStr(HardwareOut.Count - 1));
    AddMessage('Hardware link rows: ' + IntToStr(LinkOut.Count - 1));
    AddMessage('Hardware reverse-ref rows: ' + IntToStr(ReverseOut.Count - 1));
    AddMessage('Backend semantic rows: ' + IntToStr(SemanticOut.Count - 1));
  end;

  HardwareOut.Free;
  LinkOut.Free;
  ReverseOut.Free;
  SemanticOut.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  SeenLogical.Free;
  SemanticTerms.Free;
end;

end.
