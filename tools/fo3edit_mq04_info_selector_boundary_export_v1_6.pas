unit fo3edit_mq04_info_selector_boundary_export_v1_6;

{
  JANUS / Fallout 3 — MQ04 INFO selector-boundary exporter v1.6

  Read-only. Load exactly:
    Fallout3.esm
    Anchorage.esm
    ThePitt.esm
    BrokenSteel.esm
    PointLookout.esm
    Zeta.esm

  The exporter locates the winning MQ04 quest, follows the same structural
  route used by xEdit dialogue exporters:

    QUST(MQ04) -> ReferencedBy DIAL -> ChildGroup(DIAL) -> INFO

  For every effective non-deleted MQ04 INFO it writes:
    1) one index row; and
    2) all leaf values from Responses, Conditions, Script (Begin), Script (End),
       preserving linked FormIDs where xEdit can resolve them.

  This is discovery evidence only. A result-script flag assignment such as
  DadDogInfo/BraunInfo is not by itself a memory mutation or carrier write.
}

var
  IndexOut: TStringList;
  LeafOut: TStringList;
  LoadedOfficial: TStringList;
  UnexpectedPlugins: TStringList;
  SeenInfos: TStringList;
  SeenDialogs: TStringList;
  Blocked: boolean;
  FoundMQ04: boolean;
  DuplicateInfoCount: integer;

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

function EffectiveWinning(e: IInterface): IInterface;
var
  root: IInterface;
begin
  Result := nil;
  if not Assigned(e) then exit;
  root := MasterOrSelf(e);
  if not Assigned(root) then root := e;
  Result := WinningOverride(root);
  if not Assigned(Result) then Result := root;
  if GetIsDeleted(Result) then Result := nil;
end;

function SafeElementValue(e: IInterface; path: string): string;
var
  x: IInterface;
begin
  Result := '';
  if not Assigned(e) then exit;
  x := ElementByPath(e, path);
  if Assigned(x) then Result := CleanTSV(GetEditValue(x));
end;

function ResolveLinked(e: IInterface): IInterface;
begin
  Result := nil;
  if not Assigned(e) then exit;
  Result := LinksTo(e);
  if Assigned(Result) then begin
    Result := EffectiveWinning(Result);
  end;
end;

procedure EmitLeaf(info, dial, el: IInterface; section: string);
var
  value, nm, pth: string;
  linked: IInterface;
  linkedFile, linkedSig, linkedID, linkedEDID: string;
begin
  if not Assigned(el) then exit;
  value := GetEditValue(el);
  if value = '' then exit;

  nm := Name(el);
  pth := Path(el);

  { Compiled embedded scripts can be verbose hex. Preserve presence and a
    bounded prefix; Script Source / references remain intact unless extreme. }
  if (Pos('Compiled', nm) > 0) and (Length(value) > 4096) then
    value := Copy(value, 1, 4096) + '...[TRUNCATED_COMPILED_BYTES]'
  else if Length(value) > 16384 then
    value := Copy(value, 1, 16384) + '...[TRUNCATED_VALUE]';

  linkedFile := '';
  linkedSig := '';
  linkedID := '';
  linkedEDID := '';
  linked := ResolveLinked(el);
  if Assigned(linked) then begin
    linkedFile := GetFileName(GetFile(linked));
    linkedSig := Signature(linked);
    linkedID := Hex8(GetLoadOrderFormID(linked));
    linkedEDID := EditorID(linked);
  end;

  LeafOut.Add(
    Hex8(GetLoadOrderFormID(MasterOrSelf(info))) + #9 +
    Hex8(GetLoadOrderFormID(MasterOrSelf(dial))) + #9 +
    CleanTSV(section) + #9 +
    CleanTSV(pth) + #9 +
    CleanTSV(nm) + #9 +
    CleanTSV(value) + #9 +
    CleanTSV(linkedFile) + #9 +
    CleanTSV(linkedSig) + #9 +
    CleanTSV(linkedID) + #9 +
    CleanTSV(linkedEDID)
  );
end;

procedure ExportLeaves(info, dial, el: IInterface; section: string; depth: integer);
var
  i, n: integer;
  child: IInterface;
begin
  if not Assigned(el) then exit;
  if depth > 40 then exit;

  n := ElementCount(el);
  if n > 0 then begin
    for i := 0 to n - 1 do begin
      child := ElementByIndex(el, i);
      if Assigned(child) then ExportLeaves(info, dial, child, section, depth + 1);
    end;
  end else
    EmitLeaf(info, dial, el, section);
end;

procedure ExportInfo(info, dial: IInterface);
var
  rootInfo, winInfo, speakerEl, speaker: IInterface;
  logicalID, speakerRaw, speakerID, speakerEDID: string;
begin
  rootInfo := MasterOrSelf(info);
  if not Assigned(rootInfo) then rootInfo := info;
  logicalID := Hex8(GetLoadOrderFormID(rootInfo));

  if SeenInfos.IndexOf(logicalID) >= 0 then begin
    DuplicateInfoCount := DuplicateInfoCount + 1;
    exit;
  end;
  SeenInfos.Add(logicalID);

  winInfo := EffectiveWinning(rootInfo);
  if not Assigned(winInfo) then exit;

  speakerRaw := SafeElementValue(winInfo, 'ANAM - Speaker');
  speakerID := '';
  speakerEDID := '';
  speakerEl := ElementByPath(winInfo, 'ANAM - Speaker');
  speaker := ResolveLinked(speakerEl);
  if Assigned(speaker) then begin
    speakerID := Hex8(GetLoadOrderFormID(speaker));
    speakerEDID := EditorID(speaker);
  end;

  IndexOut.Add(
    logicalID + #9 +
    CleanTSV(GetFileName(GetFile(winInfo))) + #9 +
    Hex8(GetLoadOrderFormID(MasterOrSelf(dial))) + #9 +
    CleanTSV(EditorID(dial)) + #9 +
    CleanTSV(Name(dial)) + #9 +
    CleanTSV(speakerRaw) + #9 +
    CleanTSV(speakerID) + #9 +
    CleanTSV(speakerEDID) + #9 +
    SafeElementValue(winInfo, 'TPIC - Previous Topic') + #9 +
    SafeElementValue(winInfo, 'PNAM - Previous INFO') + #9 +
    CleanTSV(FullPath(winInfo))
  );

  ExportLeaves(winInfo, dial, ElementByName(winInfo, 'Responses'), 'RESPONSES', 0);
  ExportLeaves(winInfo, dial, ElementByName(winInfo, 'Conditions'), 'CONDITIONS', 0);
  ExportLeaves(winInfo, dial, ElementByName(winInfo, 'Script (Begin)'), 'BEGIN_SCRIPT', 0);
  ExportLeaves(winInfo, dial, ElementByName(winInfo, 'Script (End)'), 'END_SCRIPT', 0);
end;

procedure ExportDialog(dial: IInterface);
var
  rootDial, winDial, infoGroup, info: IInterface;
  i: integer;
  logicalID: string;
begin
  rootDial := MasterOrSelf(dial);
  if not Assigned(rootDial) then rootDial := dial;
  logicalID := Hex8(GetLoadOrderFormID(rootDial));
  if SeenDialogs.IndexOf(logicalID) >= 0 then exit;
  SeenDialogs.Add(logicalID);

  winDial := EffectiveWinning(rootDial);
  if not Assigned(winDial) then exit;

  { ChildGroup on the logical topic preserves the INFO population; each INFO
    is independently resolved to its effective winning record in ExportInfo. }
  infoGroup := ChildGroup(rootDial);
  if not Assigned(infoGroup) then exit;
  for i := 0 to ElementCount(infoGroup) - 1 do begin
    info := ElementByIndex(infoGroup, i);
    if Assigned(info) and (Signature(info) = 'INFO') then
      ExportInfo(info, winDial);
  end;
end;

procedure ExportMQ04Quest(quest: IInterface);
var
  rootQuest, winQuest, r: IInterface;
  i, n: integer;
begin
  rootQuest := MasterOrSelf(quest);
  if not Assigned(rootQuest) then rootQuest := quest;
  winQuest := EffectiveWinning(rootQuest);
  if not Assigned(winQuest) then exit;

  FoundMQ04 := true;
  n := ReferencedByCount(rootQuest);
  for i := 0 to n - 1 do begin
    r := ReferencedByIndex(rootQuest, i);
    if Assigned(r) and (Signature(r) = 'DIAL') then
      ExportDialog(r);
  end;
end;

function Initialize: integer;
var
  i: integer;
  f: IInterface;
  fn: string;
begin
  Result := 0;
  Blocked := false;
  FoundMQ04 := false;
  DuplicateInfoCount := 0;

  IndexOut := TStringList.Create;
  LeafOut := TStringList.Create;
  LoadedOfficial := TStringList.Create;
  UnexpectedPlugins := TStringList.Create;
  SeenInfos := TStringList.Create;
  SeenDialogs := TStringList.Create;

  LoadedOfficial.Sorted := true;
  LoadedOfficial.Duplicates := dupIgnore;
  UnexpectedPlugins.Sorted := true;
  UnexpectedPlugins.Duplicates := dupIgnore;
  SeenInfos.Sorted := true;
  SeenInfos.Duplicates := dupIgnore;
  SeenDialogs.Sorted := true;
  SeenDialogs.Duplicates := dupIgnore;

  if CompareText(wbAppName, 'FO3') <> 0 then begin
    AddMessage('JANUS MQ04 INFO v1.6 BLOCKED: xEdit is not running in FO3 mode.');
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
    AddMessage('JANUS MQ04 INFO v1.6 BLOCKED: expected six official masters, found ' + IntToStr(LoadedOfficial.Count) + '.');
    Blocked := true;
  end;
  if UnexpectedPlugins.Count > 0 then begin
    AddMessage('JANUS MQ04 INFO v1.6 BLOCKED: non-official plugins are loaded.');
    Blocked := true;
  end;

  IndexOut.Add(
    'info_logical_formid' + #9 +
    'winning_file' + #9 +
    'topic_logical_formid' + #9 +
    'topic_editorid' + #9 +
    'topic_name' + #9 +
    'speaker_raw' + #9 +
    'speaker_formid' + #9 +
    'speaker_editorid' + #9 +
    'previous_topic_raw' + #9 +
    'previous_info_raw' + #9 +
    'full_path'
  );

  LeafOut.Add(
    'info_logical_formid' + #9 +
    'topic_logical_formid' + #9 +
    'section' + #9 +
    'element_path' + #9 +
    'element_name' + #9 +
    'element_value' + #9 +
    'linked_file' + #9 +
    'linked_signature' + #9 +
    'linked_formid' + #9 +
    'linked_editorid'
  );

  AddMessage('JANUS MQ04 INFO selector-boundary exporter v1.6 initialized.');
end;

function Process(e: IInterface): integer;
var
  win: IInterface;
begin
  Result := 0;
  if Blocked then exit;
  if ElementType(e) <> etMainRecord then exit;
  if Signature(e) <> 'QUST' then exit;
  if CompareText(EditorID(e), 'MQ04') <> 0 then exit;

  win := EffectiveWinning(e);
  if Assigned(win) and (CompareText(EditorID(win), 'MQ04') = 0) then
    ExportMQ04Quest(win);
end;

function Finalize: integer;
var
  indexFn, leafFn: string;
begin
  Result := 0;

  if Blocked then begin
    AddMessage('JANUS MQ04 INFO v1.6 export NOT WRITTEN: admission prerequisites failed.');
  end else if not FoundMQ04 then begin
    AddMessage('JANUS MQ04 INFO v1.6 export NOT WRITTEN: MQ04 quest was not found.');
  end else if DuplicateInfoCount <> 0 then begin
    AddMessage('JANUS MQ04 INFO v1.6 export NOT WRITTEN: duplicate logical INFO count = ' + IntToStr(DuplicateInfoCount));
  end else begin
    indexFn := ScriptsPath + 'JANUS-MQ04-INFO-Index-v1.6.tsv';
    leafFn := ScriptsPath + 'JANUS-MQ04-INFO-Embedded-Control-v1.6.tsv';
    IndexOut.SaveToFile(indexFn);
    LeafOut.SaveToFile(leafFn);
    AddMessage('MQ04 INFO rows: ' + IntToStr(IndexOut.Count - 1));
    AddMessage('MQ04 INFO leaf rows: ' + IntToStr(LeafOut.Count - 1));
    AddMessage('Index: ' + indexFn);
    AddMessage('Embedded-control leaves: ' + leafFn);
  end;

  IndexOut.Free;
  LeafOut.Free;
  LoadedOfficial.Free;
  UnexpectedPlugins.Free;
  SeenInfos.Free;
  SeenDialogs.Free;
end;

end.
